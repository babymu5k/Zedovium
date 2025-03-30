# pool_server_fixed.py
import json
import time
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Lock
from collections import defaultdict
import requests

class MiningPool:
    def __init__(self, node_url, reward_address, fee_percent=1.0):
        self.node_url = node_url.rstrip('/')
        self.reward_address = reward_address
        self.fee_percent = fee_percent
        self.miners = defaultdict(lambda: {'shares': 0, 'last_active': 0})
        self.current_work = None
        self.work_lock = Lock()
        self.share_difficulty = 8  # Easier than main chain
        self.block_time_target = 300  # 5 minutes
        self.last_block_time = time.time()
        
        # Start background tasks
        Thread(target=self.update_work_loop, daemon=True).start()
        Thread(target=self.cleanup_inactive_miners, daemon=True).start()

    def update_work(self):
        """Fetch current blockchain state"""
        try:
            # Get latest block
            block = requests.get(f"{self.node_url}/network/latestblock", timeout=5).json()
            
            # Get pending transactions
            mempool = requests.get(f"{self.node_url}/mempool/transactions", timeout=5).json()
            
            with self.work_lock:
                self.current_work = {
                    'height': block['index'] + 1,
                    'prev_hash': block['prev_hash'],
                    'prev_proof': block['proofN'],
                    'transactions': mempool.get('transactions', [])[:50],  # Limit tx count
                    'share_target': 2 ** (256 - self.share_difficulty),
                    'timestamp': time.time()
                }
            return True
        except Exception as e:
            print(f"Work update failed: {str(e)}")
            return False

    def update_work_loop(self):
        """Periodically update work unit"""
        while True:
            self.update_work()
            time.sleep(30)

    def validate_share(self, miner_id, proof):
        """Validate miner's share"""
        with self.work_lock:
            if not self.current_work:
                return {'valid': False, 'error': 'No current work'}
            
            work = self.current_work.copy()
        
        # Verify share difficulty
        guess = f"{work['prev_proof']}{proof}".encode()
        guess_hash = int(hashlib.blake2b(guess).hexdigest(), 16)
        
        if guess_hash >= work['share_target']:
            return {'valid': False, 'error': 'Low difficulty'}
        
        # Verify if it's also a valid block
        is_block = False
        try:
            block_data = {
                'index': work['height'],
                'proofN': proof,
                'prev_hash': work['prev_hash'],
                'miner_address': self.reward_address,
                'timestamp': int(time.time())
            }
            response = requests.post(
                f"{self.node_url}/mining/submitblock",
                json=block_data,
                timeout=10
            )
            is_block = response.status_code == 201
        except Exception as e:
            print(f"Block submission failed: {str(e)}")
        
        # Update miner stats
        self.miners[miner_id]['shares'] += 1
        self.miners[miner_id]['last_active'] = time.time()
        
        return {
            'valid': True,
            'block_found': is_block,
            'shares': self.miners[miner_id]['shares']
        }

    def distribute_rewards(self):
        """Distribute rewards to miners"""
        total_shares = sum(m['shares'] for m in self.miners.values())
        if total_shares == 0:
            return False
        
        try:
            # Get current block reward
            chain_info = requests.get(f"{self.node_url}/network/info", timeout=5).json()
            block_reward = chain_info.get('block_reward', 80)
            
            # Calculate rewards
            fee = (block_reward * self.fee_percent) / 100
            reward_pool = block_reward - fee
            
            # Send rewards
            for miner_id, miner_data in self.miners.items():
                if miner_data['shares'] > 0:
                    reward = (miner_data['shares'] / total_shares) * reward_pool
                    if reward > 0:
                        requests.post(
                            f"{self.node_url}/transaction/create",
                            json={
                                'sender': self.reward_address,
                                'recipient': miner_id,
                                'amount': reward,
                                'seed': 'POOL_REWARD_SEED'
                            },
                            timeout=10
                        )
            
            # Reset shares
            self.miners.clear()
            return True
        except Exception as e:
            print(f"Reward distribution failed: {str(e)}")
            return False

    def cleanup_inactive_miners(self):
        """Remove inactive miners"""
        while True:
            inactive_time = time.time() - 3600  # 1 hour threshold
            to_remove = [
                mid for mid, m in self.miners.items() 
                if m['last_active'] < inactive_time
            ]
            for mid in to_remove:
                self.miners.pop(mid)
            time.sleep(60)

class PoolHTTPHandler(BaseHTTPRequestHandler):
    def __init__(self, pool, *args, **kwargs):
        self.pool = pool
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/getwork':
            with self.pool.work_lock:
                if not self.pool.current_work:
                    self.send_error(503, 'No work available')
                    return
                
                work = {
                    'prev_proof': self.pool.current_work['prev_proof'],
                    'height': self.pool.current_work['height'],
                    'share_target': hex(self.pool.current_work['share_target'])[2:]
                }
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(work).encode())
        
        elif self.path == '/pool/stats':
            stats = {
                'miners': len(self.pool.miners),
                'total_shares': sum(m['shares'] for m in self.pool.miners.values()),
                'difficulty': self.pool.share_difficulty
            }
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode())
        
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/submitshare':
            content_length = int(self.headers['Content-Length'])
            post_data = json.loads(self.rfile.read(content_length).decode())
            
            if 'miner_id' not in post_data or 'proof' not in post_data:
                self.send_error(400, 'Missing miner_id or proof')
                return
            
            result = self.pool.validate_share(post_data['miner_id'], post_data['proof'])
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        
        else:
            self.send_error(404)

def run_pool_server(node_url, reward_address, host='0.0.0.0', port=4025):
    pool = MiningPool(node_url, reward_address)
    handler = lambda *args: PoolHTTPHandler(pool, *args)
    
    server = HTTPServer((host, port), handler)
    print(f"Pool server running on {host}:{port}")
    print(f"Connected to node: {node_url}")
    print(f"Pool fee: {pool.fee_percent}%")
    server.serve_forever()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True, help="ZED node URL")
    parser.add_argument("--address", required=True, help="Pool reward address")
    parser.add_argument("--port", type=int, default=4025, help="Pool server port")
    args = parser.parse_args()
    
    run_pool_server(args.node, args.address, port=args.port)