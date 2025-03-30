# pc_miner_fixed.py
import hashlib
import requests
import time
from threading import Thread, Lock
import argparse

class ZEDMiner:
    def __init__(self, pool_url, miner_address):
        self.pool_url = pool_url.rstrip('/')
        self.miner_address = miner_address
        self.current_work = None
        self.work_lock = Lock()
        self.running = False
        self.stats = {
            'hash_count': 0,
            'share_count': 0,
            'block_count': 0
        }

    def fetch_work(self):
        """Get new work from pool"""
        try:
            response = requests.get(f"{self.pool_url}/getwork", timeout=10)
            if response.status_code == 200:
                work = response.json()
                with self.work_lock:
                    self.current_work = {
                        'prev_proof': work['prev_proof'],
                        'height': work['height'],
                        'target': int(work['share_target'], 16)
                    }
                return True
        except Exception as e:
            print(f"Work fetch failed: {str(e)}")
        return False

    def mining_loop(self):
        """Main mining loop"""
        proof = 0
        while self.running:
            # Get current work
            with self.work_lock:
                if not self.current_work:
                    time.sleep(1)
                    continue
                work = self.current_work.copy()
            
            # Mining
            data = f"{work['prev_proof']}{proof}".encode()
            hash_result = int(hashlib.blake2b(data).hexdigest(), 16)
            self.stats['hash_count'] += 1
            
            # Check share
            if hash_result < work['target']:
                self.submit_share(proof)
                proof = 0  # Reset after successful share
            else:
                proof += 1
            
            # Update work periodically
            if proof % 100000 == 0:
                self.fetch_work()

    def submit_share(self, proof):
        """Submit share to pool"""
        try:
            response = requests.post(
                f"{self.pool_url}/submitshare",
                json={
                    'miner_id': self.miner_address,
                    'proof': proof
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                self.stats['share_count'] += 1
                if result.get('block_found', False):
                    self.stats['block_count'] += 1
                    print(f"\n🌟 BLOCK FOUND at height {self.current_work['height']} 🌟")
                return True
        except Exception as e:
            print(f"Share submission failed: {str(e)}")
        return False

    def start(self):
        """Start mining"""
        if not self.fetch_work():
            print("Failed to get initial work")
            return
        
        self.running = True
        Thread(target=self.mining_loop, daemon=True).start()
        Thread(target=self.stats_thread, daemon=True).start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            print("\nMining stopped")

    def stats_thread(self):
        """Display mining statistics"""
        last_hash_count = 0
        while self.running:
            time.sleep(10)
            hc = self.stats['hash_count']
            hashrate = (hc - last_hash_count) / 10
            last_hash_count = hc
            
            print(
                f"Hashrate: {hashrate:,.1f} H/s | "
                f"Shares: {self.stats['share_count']} | "
                f"Blocks: {self.stats['block_count']}"
            )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", required=True, help="Pool server URL")
    parser.add_argument("--address", required=True, help="ZED miner address")
    args = parser.parse_args()
    
    miner = ZEDMiner(args.pool, args.address)
    miner.start()