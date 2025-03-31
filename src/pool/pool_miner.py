# pool_miner.py
import hashlib
import time
import requests
import sys
from datetime import datetime

# Configuration
POOL_URL = "http://localhost:4025"  # Change to your pool server address
MINER_ADDRESS = "ZED-alien-ladybug-glow-garden-cecd"  # Your miner address

# ANSI color codes (same as your original)
COLORS = {
    'red': '\033[91m',
    'green': '\033[92m',
    'yellow': '\033[93m',
    'blue': '\033[94m',
    'magenta': '\033[95m',
    'cyan': '\033[96m',
    'white': '\033[97m',
    'reset': '\033[0m'
}

def clear_screen():
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()

def format_hash_rate(hash_rate):
    units = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s"]
    unit_index = 0
    while hash_rate >= 1000 and unit_index < len(units) - 1:
        hash_rate /= 1000
        unit_index += 1
    return f"{hash_rate:.2f} {units[unit_index]}"

def print_header():
    clear_screen()
    print(f"{COLORS['cyan']}╔══════════════════════════════════════════════════╗")
    print(f"║{COLORS['yellow']}       ZEDOVIUM POOL MINER v0.1.0 (Python)       {COLORS['cyan']}║")
    print(f"║{COLORS['white']}                                                  {COLORS['cyan']}║")
    print(f"║{COLORS['white']}              Created by Babymusk                 {COLORS['cyan']}║")
    print(f"║{COLORS['white']}                                                  {COLORS['cyan']}║")
    print(f"║{COLORS['white']}       Official miner for Zedovium Network        {COLORS['cyan']}║")
    print(f"╚══════════════════════════════════════════════════╝{COLORS['reset']}")
    print(f"{COLORS['blue']}⏣  Connected to pool: {COLORS['green']}{POOL_URL}")
    print(f"{COLORS['blue']}⏣  Miner address: {COLORS['yellow']}{MINER_ADDRESS}")
    print(f"{COLORS['blue']}⏣  Started at {datetime.now().strftime('%I:%M:%S')}{COLORS['reset']}")
    print("\n" + "-" * 60 + "\n")
    print(f"{COLORS['cyan']}⚙  Current Stats:{COLORS['reset']}\n")

def get_job():
    """Get current mining job from pool"""
    try:
        resp = requests.get(f"{POOL_URL}/pool/job?address={MINER_ADDRESS}")
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"{COLORS['red']}Error getting job: {e}{COLORS['reset']}")
    return None

def submit_share(nonce):
    """Submit a share to the pool"""
    try:
        resp = requests.post(
            f"{POOL_URL}/pool/submit",
            json={"address": MINER_ADDRESS, "nonce": nonce}
        )
        return resp.json()
    except Exception as e:
        print(f"{COLORS['red']}Error submitting share: {e}{COLORS['reset']}")
    return None

def mine():
    print_header()
    shares_submitted = 0
    total_hashes = 0
    start_time = time.time()
    
    while True:
        job = get_job()
        if not job:
            time.sleep(5)
            continue
            
        print(f"{COLORS['blue']}⛏  Mining at height {COLORS['yellow']}{job['height']}  {COLORS['blue']}│ {COLORS['white']}Share diff: {COLORS['yellow']}{job['share_difficulty']}  {COLORS['white']}│ Network diff: {COLORS['yellow']}{job['network_difficulty']}{COLORS['reset']}")
        
        nonce = 0
        hash_count = 0
        share_start = time.time()
        
        while True:
            # Check if we need a new job (every 1000 hashes)
            if hash_count % 1000 == 0:
                new_job = get_job()
                if new_job and new_job['height'] != job['height']:
                    job = new_job
                    break
                    
            # Hash computation
            guess = f"{job['prev_hash']}{nonce}".encode()
            guess_hash = hashlib.blake2b(guess).hexdigest()
            hash_count += 1
            total_hashes += 1
            
            # Check for share
            if guess_hash.startswith("0" * job['share_difficulty']):
                result = submit_share(nonce)
                if result and result.get('status') == 'share':
                    shares_submitted += 1
                    elapsed = time.time() - share_start
                    hash_rate = hash_count / elapsed if elapsed > 0 else 0
                    
                    print(f"{COLORS['green']}✔  Share accepted  {COLORS['white']}│ {COLORS['blue']}Hashrate: {COLORS['yellow']}{format_hash_rate(hash_rate)}  {COLORS['white']}│ {COLORS['blue']}Total shares: {COLORS['yellow']}{shares_submitted}{COLORS['reset']}")
                    
                    # Reset for next share
                    share_start = time.time()
                    hash_count = 0
                    
                elif result and result.get('status') == 'block':
                    print(f"{COLORS['magenta']}🎉  BLOCK FOUND!  {COLORS['white']}│ {COLORS['blue']}Height: {COLORS['yellow']}{job['height']}{COLORS['reset']}")
                    
            nonce += 1
            
            # Display stats periodically
            if total_hashes % 10000 == 0:
                elapsed_total = time.time() - start_time
                total_hash_rate = total_hashes / elapsed_total if elapsed_total > 0 else 0
                print(f"{COLORS['cyan']}⚙  Total hashrate: {COLORS['yellow']}{format_hash_rate(total_hash_rate)}  {COLORS['white']}│ {COLORS['cyan']}Shares: {COLORS['yellow']}{shares_submitted}{COLORS['reset']}")

if __name__ == "__main__":
    mine()