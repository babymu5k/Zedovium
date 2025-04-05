import hashlib
import time
import requests
import random
import sys
from datetime import datetime
import json


# ANSI color codes
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

# Terminal control codes
CLEAR_SCREEN = '\033[2J\033[H'
CURSOR_UP = '\033[1A'
CLEAR_LINE = '\033[2K'

config = json.load(open("src/data/config.json", "r"))

def CheckZedoGuard(node):
    """Check if ZedoGuard is active"""
    try:
        response = requests.get(f"{node}/network/info", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data["zedoguard"] == True
    except:
        pass
    return False

def clear_screen():
    sys.stdout.write(CLEAR_SCREEN)
    sys.stdout.flush()

def move_cursor_up(lines=1):
    sys.stdout.write(CURSOR_UP * lines)
    sys.stdout.flush()

def clear_lines(count=1):
    for _ in range(count):
        sys.stdout.write(CLEAR_LINE)
        move_cursor_up()
    sys.stdout.write(CLEAR_LINE)
    sys.stdout.flush()

def get_node():
    response = requests.get("https://raw.githubusercontent.com/babymu5k/Zedovium/refs/heads/develop/nodelist.json").json()
    return random.choice(response["nodes"])

def get_mining_info(node):
    response = requests.get(f"{node}/mining/info")
    return response.json()

def get_miner_difficulty(node, address):
    """Check if miner has a custom difficulty"""
    response = requests.get(f"{node}/network/checkaddrdiff/{address}")
    return response.json()

def submit_block(node, block):
    response = requests.post(f"{node}/mining/submitblock", json=block)
    return response.json()

def proof_of_work(last_proof, difficulty, warning_callback=None):
    nonce = 0
    start_time = time.time()
    last_warning_time = 0
    hashes = 0
    
    while not valid_proof(last_proof, nonce, difficulty):
        nonce += 1
        hashes += 1
        
        # Check for high hash rate every 100k hashes
        if hashes % 100000 == 0 and warning_callback:
            current_time = time.time()
            elapsed = current_time - start_time
            if elapsed > 0:
                current_rate = hashes / elapsed
                # Only warn once every 30 seconds max
                if current_time - last_warning_time > 30:
                    warning_callback(current_rate, difficulty)
                    last_warning_time = current_time
    
    end_time = time.time()
    hash_rate = nonce / (end_time - start_time) if (end_time - start_time) > 0 else 0
    return nonce, hash_rate

def check_mining_speed(node, miner_address):
    """Check if miner is going too fast and get current stats"""
    try:
        response = requests.get(f"{node}/network/checkaddrdiff/{miner_address}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('status') == 'high', data
    except:
        pass
    return False, {}

def print_speed_warning(hash_rate, current_diff):
    """Show warning about mining too fast"""
    print(f"{COLORS['yellow']}⚠  WARNING: High hash rate detected! {format_hash_rate(hash_rate)}")
    print(f"   Your miner may trigger ZedoGuard difficulty increases")
    print(f"   Current base difficulty: {current_diff}")
    print(f"   Consider throttling your miner to stay under 10 blocks/hour{COLORS['reset']}")


def valid_proof(last_proof, proof, difficulty):
    guess = f'{last_proof}{proof}'.encode()
    guess_hash = hashlib.blake2b(guess).hexdigest()
    return guess_hash[:difficulty] == "0" * difficulty

def calculate_hash(block):
    block_string = f"{block['index']}{block['proofN']}{block['prev_hash']}{block['transactions']}{block['timestamp']}"
    return hashlib.blake2b(block_string.encode()).hexdigest()

def format_hash_rate(hash_rate):
    units = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s"]
    unit_index = 0
    while hash_rate >= 1000 and unit_index < len(units) - 1:
        hash_rate /= 1000
        unit_index += 1
    return f"{hash_rate:.2f} {units[unit_index]}"
def print_header(address):
    clear_screen()
    print(f"{COLORS['cyan']}╔══════════════════════════════════════════════════╗")
    print(f"║{COLORS['yellow']}          ZEDOVIUM MINER v0.1.0 (Python)          {COLORS['cyan']}║")
    print(f"║{COLORS['white']}                                                  {COLORS['cyan']}║")
    print(f"║{COLORS['white']}              Created by Babymusk                 {COLORS['cyan']}║")
    print(f"║{COLORS['white']}                                                  {COLORS['cyan']}║")
    print(f"║{COLORS['white']}       Official miner for Zedovium Network        {COLORS['cyan']}║")
    print(f"╚══════════════════════════════════════════════════╝{COLORS['reset']}")
    print(f"{COLORS['blue']}⏣  Connected to network: {COLORS['green']}Zedovium Mainnet")
    print(f"{COLORS['blue']}⏣  Miner address: {COLORS['yellow']}{address}")
    print(f"{COLORS['blue']}⏣  Started at {datetime.now().strftime('%I:%M:%S')}{COLORS['reset']}")
    print("\n" + "-" * 60 + "\n")  # Separator line
    print(f"{COLORS['cyan']}⚙  Current Stats:{COLORS['reset']}\n")


def print_block_result(result, hash_rate, block_time):
    if isinstance(result, dict) and 'index' in result:
        # Successful block
        print(f"\n[{datetime.fromtimestamp(time.time()):%I:%M:%S}] {COLORS['green']} ✔  Block accepted!  {COLORS['white']}│ {COLORS['blue']}Hashrate: {COLORS['yellow']}{format_hash_rate(hash_rate)} {COLORS['white']}│ {COLORS['blue']}Time: {COLORS['yellow']}{block_time:.2f}s{COLORS['reset']} │ {COLORS['blue']}New height: {COLORS['yellow']}{result['index']}{COLORS['reset']}")
    else:
        # Failed block - handle different error formats
        if isinstance(result, dict):
            if result.get('status') == 'error':
                reason = result.get('message', 'Unknown error')
                if 'required_difficulty' in result:
                    reason += f" (Current multiplier: {result.get('your_difficulty_multiplier', 1.0)}x)"
            else:
                reason = str(result)
        else:
            reason = str(result)
            
        print(f"\n{COLORS['red']}✖  Block rejected  {COLORS['white']}│ {COLORS['blue']}Reason: {COLORS['yellow']}{reason}{COLORS['reset']}")
        print(f"{COLORS['cyan']}   Tip: Try reducing your mining speed to lower your difficulty multiplier{COLORS['reset']}\n")

def print_mining_stats(diff, hash_rate, block_height, blocks_mined):
    if blocks_mined % 5 == 0:  # Only show stats every 5 blocks
        print(f"\n{COLORS['green']}⚙  Mining info  {COLORS['white']}│ {COLORS['blue']}Difficulty: {COLORS['yellow']}{diff} {COLORS['white']}│ {COLORS['blue']}Hashrate: {COLORS['yellow']}{format_hash_rate(hash_rate)} {COLORS['white']}│ {COLORS['blue']}Height: {COLORS['yellow']}{block_height}{COLORS['reset']}")

def mine(zedoguard_active):
    node = get_node()
    print_header(config["address"])
    miner_address = config["address"]
    blocks_mined = 0  # Add counter for mined blocks
    blocks_mined = 0
    last_speed_check = 0
    
    while True:
        try:
        #     # Check if we're mining too fast (every 5 minutes)
        #     current_time = time.time()
        #     if zedoguard_active:
        #         if current_time - last_speed_check > 300:  # 5 minutes
        #             is_too_fast, diff_info = check_mining_speed(node, miner_address)
        #             if is_too_fast:
        #                 print(f"\n{COLORS['red']}⛔  ZEDOGUARD ACTIVE  {COLORS['white']}│ {COLORS['blue']}Your difficulty: {COLORS['yellow']}{diff_info['effective_difficulty']}x {COLORS['white']}(base: {diff_info['base_difficulty']})")
        #                 print(f"{COLORS['red']}   You're mining {diff_info['current_blocks_per_hour']} blocks/hour (threshold: {diff_info['threshold']})")
        #                 print(f"{COLORS['yellow']}   Consider slowing down your miner{COLORS['reset']}\n")
        #             last_speed_check = current_time
        #         else:
        #             pass
        #     elif not(zedoguard_active):
        #         continue
                
            # Get current mining info
            mining_data = get_mining_info(node)
            latest_block = mining_data["latestblock"]
            base_difficulty = mining_data["difficulty"]
            
            # Check our personal difficulty
            diff_info = get_miner_difficulty(node, miner_address)
            current_diff = diff_info.get('effective_difficulty', base_difficulty)
            
            last_proof = latest_block["proofN"]
            
            if zedoguard_active:
                warning = lambda rate, diff: print_speed_warning(rate, diff)
            else:
                warning = None
            
            # Start mining with warning callback
            start_time = time.time()
            proof, hash_rate = proof_of_work(
                last_proof, 
                current_diff,
                warning
            )
            block_time = time.time() - start_time
            
            # Print mining stats
            print_mining_stats(current_diff, hash_rate, latest_block["index"], blocks_mined)
            
            # Check if block is still valid
            new_mining_data = get_mining_info(node)
            if new_mining_data["latestblock"]["index"] != latest_block["index"]:
                print(f"{COLORS['yellow']}⚠  New block found by another miner. Restarting...{COLORS['reset']}")
                time.sleep(1)
                continue
            
            # Prepare and submit block
            new_block = {
                "index": latest_block["index"] + 1,
                "proofN": proof,
                "prev_hash": calculate_hash(latest_block),
                "miner_address": miner_address,
                "timestamp": time.time()
            }
            
            result = submit_block(node, new_block)
            if isinstance(result, dict) and 'index' in result:
                blocks_mined += 1
            print_block_result(result, hash_rate, block_time)
            
            time.sleep(1)
            
        except Exception as e:
            print(f"{COLORS['red']}⚠  Connection error: {e}. Reconnecting...{COLORS['reset']}")
            time.sleep(5)
            node = get_node()

if __name__ == "__main__":
    clear_screen()
    zedoguard_active = CheckZedoGuard(get_node())
    mine(zedoguard_active)