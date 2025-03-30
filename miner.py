import hashlib
import time
import requests
import random
#from termcolor import colored

def getnode():
    response = requests.get("https://raw.githubusercontent.com/babymu5k/Zedovium/refs/heads/develop/nodelist.json").json()
    return random.choice(response["nodes"])

nodelist = getnode()

def get_mining():
    response = requests.get(f"{nodelist}/mining/info")
    return response.json()

def submit_block(block):
    response = requests.post(f"{nodelist}/mining/submitblock", json=block)
    return response.json()

def proof_of_work(last_proof, difficulty):
    nonce = 0
    start_time = time.time()
    while not valid_proof(last_proof, nonce, difficulty):
        nonce += 1
        end_time = time.time()
        total_time = end_time - start_time
        hash_rate = nonce / total_time if total_time > 0 else 0
    return nonce, hash_rate

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

def mine():
    while True:
        mining_data = get_mining()
        latest_block = mining_data["latestblock"]
        difficulty = mining_data["difficulty"]
        last_proof = latest_block["proofN"]
        proof, hash_rate = proof_of_work(last_proof, difficulty)

        # Check for the latest block before submitting
        new_mining_data = get_mining()
        new_latest_block = new_mining_data["latestblock"]

        if new_latest_block["index"] != latest_block["index"]:
            print("New block found by another miner. Restarting mining process.")
            continue

        new_block = {
        "index": latest_block["index"] + 1,
        "proofN": proof,
        "prev_hash": calculate_hash(latest_block),
        "miner_address": "ZED-alien-ladybug-glow-garden-cecd",  # Add transactions if any
        "timestamp": time.time()
        }

        result = submit_block(new_block)
        formatted_hash_rate = format_hash_rate(hash_rate)
        print(f"Block submitted: {result}")
        print(f"Hash rate: {formatted_hash_rate}")
        
        mining_data = get_mining()
        time.sleep(5)

print(getnode())
if __name__ == "__main__":
    mine()
