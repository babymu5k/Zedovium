# pool_server.py
import hashlib
import time
import json
import secrets, requests
from datetime import datetime
from collections import defaultdict
from sanic import Sanic, response
from sanic_ext import openapi

# Configuration
POOL_FEE_PERCENT = 1.0  # 1% pool fee
PAYOUT_THRESHOLD = 100  # Minimum ZED balance before payout
BLOCK_REWARD = 80  # From your blockchain constants
SHARE_DIFFICULTY = 4  # Lower than network difficulty for frequent shares

app = Sanic("ZedoviumPool")
pool = None

class Pool:
    def __init__(self):
        self.miners = {}  # {address: {shares: int, last_share: timestamp, balance: float}}
        self.blocks = []  # Mined blocks waiting for confirmation
        self.shares = defaultdict(int)  # Temporary share counting for current round
        self.current_job = None
        self.last_block_update = 0
        self.node_url = "http://localhost:4024"  # Default to local node
        
    def update_job(self):
        """Get current mining job from blockchain node"""
        try:
            resp = requests.get(f"{self.node_url}/mining/info")
            if resp.status_code == 200:
                data = resp.json()
                self.current_job = {
                    'height': data['latestblock']['index'] + 1,
                    'prev_hash': data['latestblock']['prev_hash'],
                    'difficulty': data['difficulty'],
                    'timestamp': time.time()
                }
                self.last_block_update = time.time()
        except Exception as e:
            print(f"Error updating job: {e}")

    def add_share(self, miner_address, nonce, share_difficulty):
        """Validate and record a share from a miner"""
        if not self.current_job:
            return False
            
        # Validate the share meets the required difficulty
        if not self.valid_share(nonce, share_difficulty):
            return False
            
        # Initialize miner if new
        if miner_address not in self.miners:
            self.miners[miner_address] = {
                'shares': 0,
                'last_share': time.time(),
                'balance': 0.0,
                'pending_payout': 0.0
            }
            
        # Update miner stats
        self.miners[miner_address]['shares'] += 1
        self.miners[miner_address]['last_share'] = time.time()
        self.shares[miner_address] += 1
        
        return True
        
    def valid_share(self, nonce, share_difficulty):
        """Check if a share meets the required difficulty"""
        if not self.current_job:
            return False
            
        guess = f"{self.current_job['prev_hash']}{nonce}".encode()
        guess_hash = hashlib.blake2b(guess).hexdigest()
        return guess_hash.startswith("0" * share_difficulty)
        
    def submit_block(self, miner_address, nonce):
        """Submit a found block to the network"""
        if not self.current_job:
            return False
            
        # Verify the block meets network difficulty
        if not self.valid_share(nonce, self.current_job['difficulty']):
            return False
            
        # Prepare block submission
        block_data = {
            "index": self.current_job['height'],
            "proofN": nonce,
            "prev_hash": self.current_job['prev_hash'],
            "miner_address": miner_address,
            "timestamp": time.time()
        }
        
        try:
            resp = requests.post(
                f"{self.node_url}/mining/submitblock",
                json=block_data,
                timeout=10
            )
            
            if resp.status_code == 200:
                # Block accepted, distribute rewards
                self.distribute_rewards(miner_address)
                return True
                
        except Exception as e:
            print(f"Error submitting block: {e}")
            
        return False
        
    def distribute_rewards(self, finder_address):
        """Distribute block rewards to miners"""
        total_shares = sum(self.shares.values())
        if total_shares == 0:
            return
            
        # Calculate pool fee
        pool_fee = BLOCK_REWARD * (POOL_FEE_PERCENT / 100)
        remaining_reward = BLOCK_REWARD - pool_fee
        
        # Distribute to miners proportionally
        for address, shares in self.shares.items():
            reward = (shares / total_shares) * remaining_reward
            self.miners[address]['pending_payout'] += reward
            
        # Bonus for block finder (5% of remaining reward)
        finder_bonus = remaining_reward * 0.05
        self.miners[finder_address]['pending_payout'] += finder_bonus
        
        # Reset shares for next round
        self.shares.clear()
        
    def process_payouts(self):
        """Send accumulated balances to miners"""
        for address, miner in self.miners.items():
            if miner['pending_payout'] >= PAYOUT_THRESHOLD:
                # In a real implementation, we'd send the transaction here
                print(f"Would pay {miner['pending_payout']} ZED to {address}")
                miner['balance'] += miner['pending_payout']
                miner['pending_payout'] = 0

# Initialize pool
pool = Pool()

# Pool API Endpoints
@app.get("/pool/stats")
@openapi.description("Get pool statistics")
async def pool_stats(request):
    return response.json({
        "miners": len(pool.miners),
        "current_height": pool.current_job['height'] if pool.current_job else 0,
        "total_shares": sum(m['shares'] for m in pool.miners.values()),
        "pool_fee": POOL_FEE_PERCENT,
        "payout_threshold": PAYOUT_THRESHOLD
    })

@app.get("/pool/job")
@openapi.description("Get current mining job")
async def get_job(request):
    miner_address = request.args.get("address")
    if not miner_address or not AddressGen.validate(miner_address):
        return response.json({"error": "Invalid miner address"}, status=400)
        
    # Update job if stale
    if time.time() - pool.last_block_update > 30:
        pool.update_job()
        
    if not pool.current_job:
        return response.json({"error": "No current job available"}, status=503)
        
    return response.json({
        "height": pool.current_job['height'],
        "prev_hash": pool.current_job['prev_hash'],
        "share_difficulty": SHARE_DIFFICULTY,
        "network_difficulty": pool.current_job['difficulty']
    })

@app.post("/pool/submit")
@openapi.description("Submit a mining share or block")
async def submit_share(request):
    data = request.json
    miner_address = data.get("address")
    nonce = data.get("nonce")
    
    if not miner_address or not nonce:
        return response.json({"error": "Missing parameters"}, status=400)
        
    # Check if it's a valid share first
    if pool.add_share(miner_address, nonce, SHARE_DIFFICULTY):
        # Check if it's also a valid block
        if pool.valid_share(nonce, pool.current_job['difficulty']):
            if pool.submit_block(miner_address, nonce):
                return response.json({
                    "status": "block",
                    "message": "Block found and submitted!"
                })
            else:
                return response.json({
                    "status": "error",
                    "message": "Block submission failed"
                }, status=500)
                
        return response.json({"status": "share", "message": "Share accepted"})
    else:
        return response.json({"error": "Invalid share"}, status=400)

@app.get("/pool/miner/<address>")
@openapi.description("Get miner statistics")
async def miner_stats(request, address):
    if address not in pool.miners:
        return response.json({"error": "Miner not found"}, status=404)
        
    miner = pool.miners[address]
    return response.json({
        "shares": miner['shares'],
        "pending_payout": miner['pending_payout'],
        "balance": miner['balance'],
        "last_share": miner['last_share']
    })

if __name__ == "__main__":
    # Start job updater
    pool.update_job()
    
    # Run pool server
    app.run(host="0.0.0.0", port=4025)