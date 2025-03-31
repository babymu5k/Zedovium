"""
    main.py handles the core blockchain
    Copyright (C) 2024 Babymusk

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WAsRRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

"""


import hashlib
import os
import secrets
import time

import requests
import sanic_jinja2
import ujson as jsonify
from jinja2 import FileSystemLoader
from sanic import Sanic
from sanic.response import json, text
from sanic_ext import openapi
from termcolor import colored
from web3 import Web3

with open("src/data/words.txt") as f:
    WORDLIST = [line.strip() for line in f]
    f.close()
    
class MempoolError(Exception):
    pass

class MempoolFullError(MempoolError):
    pass

class DuplicateTxError(MempoolError):
    pass


class Mempool:
    def __init__(self, max_size=10000, block_tx_limit=512):
        self.transactions = []
        self.max_size = max_size  # Prevent memory overload
        self.block_tx_limit = block_tx_limit
        # Dynamic Fees
        self.base_fee = 0.01
        self.max_fee = 0.05
        self.fee_step = 0.001

    def get_current_fee_percent(self):
        """Calculate dynamic fee based on mempool fullness"""
        mempool_fullness = len(self.transactions) / self.max_size
        # Linear scaling between base and max fee
        dynamic_fee = min(
            self.base_fee + (mempool_fullness * 
                                   (self.max_fee - self.base_fee)),
            self.max_fee
        )
        # Round to nearest step for cleaner UX
        return round(dynamic_fee / self.fee_step) * self.fee_step
        
    def add_transaction(self, tx):
        """Add transaction with basic validation"""
        if len(self.transactions) >= self.max_size:
            raise MempoolFullError("Mempool at capacity")
        
        # Check for duplicates
        if any(t['txid'] == tx['txid'] for t in self.transactions):
            raise DuplicateTxError("Transaction already in mempool")
            
        self.transactions.append(tx)
    
    def get_block_candidates(self):
        """Select transactions for next block"""
        sorted_txs = sorted(
            self.transactions,
            key=lambda x: x.get('fee', 0), 
            reverse=True
        )
        return sorted_txs[:self.block_tx_limit]
    
    def remove_confirmed(self, block_txs):
        """Remove mined transactions"""
        txids = {tx['txid'] for tx in block_txs}
        self.transactions = [
            tx for tx in self.transactions 
            if tx['txid'] not in txids
        ]


class AddressGen:
    @staticmethod
    def generate(seed=None):
        """Create a beautiful deterministic address"""
        seed = seed or secrets.token_hex(16)  # 16 random bytes if no seed
        
        # Hash the seed
        seed_hash = hashlib.sha256(seed.encode()).digest()
        
        # Convert to 4 words (from BIP-39 wordlist)
        word_indices = [
            int.from_bytes(seed_hash[i:i+2], 'big') % len(WORDLIST)
            for i in range(0, 8, 2)
        ]
        words = [WORDLIST[i] for i in word_indices]
        
        # Generate checksum (first 4 chars of hash)
        phrase = "-".join(words)
        checksum = hashlib.sha256(phrase.encode()).hexdigest()[:4]
        
        return {
            "address": f"ZED-{phrase}-{checksum}",
            "seed": seed,  # Keep this secret!
        }

    @staticmethod
    def validate(address):
        """Check if an address is valid"""
        if not address.startswith("ZED-"):
            return False
        
        parts = address.split("-")
        if len(parts) != 6:  # ZED + 4 words + checksum
            return False
        
        checksum = parts[-1]
        phrase = "-".join(parts[1:-1])
        
        # Verify checksum
        expected_checksum = hashlib.sha256(phrase.encode()).hexdigest()[:4]
        return checksum == expected_checksum

    @staticmethod
    def verify_ownership(claimed_address, seed):
        """Verify that seed generates the claimed address"""
        generated_address = AddressGen.generate(seed)["address"]
        return generated_address == claimed_address

class Block:

    def __init__(self, index, proofN, prev_hash, transactions, timestamp=None):
        self.index = index
        self.proofN = proofN
        self.prev_hash = prev_hash
        self.transactions = transactions
        self.timestamp = timestamp or time.time()

    @property
    def calculate_hash(self):
        block_of_string = "{}{}{}{}{}".format(self.index, self.proofN,
                                              self.prev_hash, self.transactions,
                                              self.timestamp)

        return hashlib.blake2b(block_of_string.encode()).hexdigest()

    def __repr__(self):
        return "{} - {} - {} - {} - {}".format(self.index, self.proofN,
                                               self.prev_hash, self.transactions,
                                               self.timestamp)

    def to_dict(self):
        return {
            'index': self.index,
            'proofN': self.proofN,
            'prev_hash': self.prev_hash,
            'transactions': self.transactions,
            'timestamp': self.timestamp,
    }

    @classmethod
    def from_dict(cls, block_dict):
        return cls(
            index=block_dict['index'],
            proofN=block_dict['proofN'],
            prev_hash=block_dict['prev_hash'],
            transactions=block_dict['transactions'],
            timestamp=block_dict['timestamp'],
        )

class BlockChain:

    def __init__(self):
        self.chain = self.LoadDB()
        self.mempool = Mempool()
        self.current_transactions = []
        self.nodes = set()
        self.diff = 1  # Initial difficulty
        self.block_time_target = 5 * 60 # 5 minutes in seconds
        self.adjustment_interval = 12  # Adjust every 12 blocks/ one hour

        self.rewards = 80 # Rewards for every block
        self.construct_genesis()
        self.diff = self.adjust_difficulty()
        self.save_flag = True  # Flag to control saving
        if not hasattr(self, 'balances'):
            self.balances = {}
        
        self.totalsupply = self.GetSupply() # Warning this variable only gives tsupply of init
        self.block_hash_map = {block.calculate_hash: block for block in self.chain}
        # Web3 compatibility
        self.CHAIN_ID = 20243
        self.SYMBOL = "ZED"
        self.DECIMAL = 18
        
        # Zedovium Guard
        self.miner_stats = {}  # Track miner performance
        self.zedoguard_threshold = 10  # Blocks per hour considered "high power"
        self.zedoguard_window = 5 * 60  # 5 minute window for stats
        self.zedoguard = False # Enable Zedovium Guard
        
        # Tokens #TODO: Add later
        self.tokens = {} # Format: {token_id: {"name": str, "symbol": str, "supply": int, "creator": str, "balances": {address: amount}}}
        
        # Transactions Fees
        self.transaction_fees = 0.035  # 3.5% transaction fee
        self.transaction_fee_address = self.GetConfig()[0]  # Address to receive transaction fees        
        
    def update_miner_stats(self, miner_address):
        """Track how often a miner successfully mines blocks"""
        now = time.time()
        
        # Initialize miner stats if not exists
        if miner_address not in self.miner_stats:
            self.miner_stats[miner_address] = {
                'blocks': [],
                'multiplier': 1.0  # Default no multiplier
            }
        
        # Add this block to miner's history
        self.miner_stats[miner_address]['blocks'].append(now)
        
        # Always clean up old blocks first (outside our 5-minute window)
        self.miner_stats[miner_address]['blocks'] = [
            t for t in self.miner_stats[miner_address]['blocks'] 
            if now - t < self.zedoguard_window
            
            ]

        # Add this block to miner's history if it's a new block
        if miner_address != "node":  # Don't track node's mining
            self.miner_stats[miner_address]['blocks'].append(now)
        
        # Calculate blocks in current window
        blocks_in_window = len(self.miner_stats[miner_address]['blocks'])
        
        # Reset multiplier if below threshold
        if blocks_in_window <= self.zedoguard_threshold:
            self.miner_stats[miner_address]['multiplier'] = 1.0
        else:
            # Apply multiplier if miner is too fast
            excess = blocks_in_window - self.zedoguard_threshold
            self.miner_stats[miner_address]['multiplier'] = 1.0 + (excess * 0.5)
            
    def get_miner_difficulty(self, miner_address):
        """Get adjusted difficulty for a miner"""
        if miner_address not in self.miner_stats:
            return self.diff  # Default difficulty
            
        # Always check current activity first
        now = time.time()
        recent_blocks = [
            t for t in self.miner_stats[miner_address]['blocks']
            if now - t < self.zedoguard_window
        ]
        
        # If no recent blocks, reset to normal
        if not recent_blocks:
            self.miner_stats[miner_address]['multiplier'] = 1.0
        if self.zedoguard:
            return int(self.diff * self.miner_stats[miner_address]['multiplier'])
        else:
            return int(self.diff * 1.0)  # No multiplier if Zedovium Guard is off
    
    def adjust_difficulty(self):
        if len(self.chain) % self.adjustment_interval == 0 and len(self.chain) > 0:
            actual_time = self.chain[-1].timestamp - self.chain[-self.adjustment_interval].timestamp
            expected_time = self.block_time_target * self.adjustment_interval
            ratio = actual_time / expected_time
            
            if ratio < 1:
                self.diff += 1
            elif ratio > 1:
                self.diff = max(1, self.diff -1)

            print(colored(f"Difficulty readjusted to {self.diff}", "blue"))
            
        return self.diff
            
    def GetSupply(self):
        return sum(list(self.balances.values()))
            
    def SaveDB(self):
        """Only save when chain has changed"""
        if not self.save_flag:
            return
            
        # Use atomic write to prevent corruption
        temp_path = "src/data/blockchain.json.tmp"
        with open(temp_path, "w") as f:
            jsonify.dump([block.to_dict() for block in self.chain], f)
        
        # Atomic rename (works on Unix/Windows)
        os.replace(temp_path, "src/data/blockchain.json")
        #print(colored("Blockchain Database SAVED!", "green"))
            
    def LoadDB(self):
        self.save_flag = False
        if os.path.exists("src/data/blockchain.json"):
            print(colored("Blockchain Database FOUND!", "green"))
            db = jsonify.load(open("src/data/blockchain.json", "r"))
            chain = [Block.from_dict(block_dict) for block_dict in db]
            #print(chain)
            self.balances = self.replay_transactions(chain)
            return chain
        else:
            print(colored("Couldnt Find A DB in src/data/ :("))
            return []
    
    def replay_transactions(self, chain):
        balances = {}
        for block in chain:
            for transaction in block.transactions:
                sender = transaction['sender']
                recipient = transaction['recipient']
                amount = transaction['quantity']
                
                balances[sender] = balances.get(sender, 0) - amount
                balances[recipient] = balances.get(recipient, 0) + amount
        
        balances["node"] = 0 # Null the node
        print(colored("PLAYED ALL TX's Successfully", "green"))
        return balances

    def construct_genesis(self):
        if not self.chain:
            print(colored("CREATING THE GENESIS", "green"))
            self.construct_block(proofN=0, prev_hash=0)

    def construct_block(self, proofN, prev_hash):
        transactions = self.mempool.get_block_candidates()
        total_fees = sum(tx['fee'] for tx in transactions if 'fee' in tx)
        
        # Update balances for transaction fees
        if total_fees > 0:
            self.balances[self.transaction_fee_address] = self.balances.get(self.transaction_fee_address, 0) + total_fees
            
        block = Block(
            index=len(self.chain),
            proofN=proofN,
            prev_hash=prev_hash,
            transactions=self.mempool.get_block_candidates())
        self.current_transactions = []

        self.chain.append(block)
        try:
            self.block_hash_map[block.calculate_hash] = block  # Add to hash map
        except AttributeError:
            pass
        
        if self.save_flag:
            self.SaveDB()
        
        self.adjust_difficulty()  # Adjust difficulty after adding a new block
        self.mempool.remove_confirmed(block.transactions)  # Remove confirmed transactions

        return block

    @staticmethod
    def check_validity(block, prev_block):

        
        if prev_block.index + 1 != block.index:
            return False

        elif prev_block.calculate_hash != block.prev_hash:
            return False

        
        elif not BlockChain.verifying_proof(block.proofN,
                                            prev_block.proofN):
            return False

        elif block.timestamp <= prev_block.timestamp:
            return False

        return True

    def calculate_txid(self, timestamp, index):
        tx_string = "{}{}".format(timestamp, index)
        return hashlib.blake2b(tx_string.encode()).hexdigest()   

    def new_transaction(self, sender, recipient, quantity, seed):
        """Add a signed transaction"""
        # 1. Validate addresses
        if not AddressGen.validate(sender) or not AddressGen.validate(recipient):
            return {"status": False, "txid": None, "error": "Invalid address(es)"}

        # Verify seed matches sender_address
        if not AddressGen.verify_ownership(sender, seed):
            return False


        status = self.new_data(
            sender=sender,
            recipient=recipient,
            quantity=quantity
        )
        
        return status

    def new_data(self, sender, recipient, quantity): # Used for appending/updating transactions to blc
        current_fee_percent = self.mempool.get_current_fee_percent()
        fee = quantity * current_fee_percent
        totaltxspend = quantity + fee
        
        pending_spends = sum(
            tx['quantity'] * (1 + self.mempool.get_current_fee_percent()) for tx in self.mempool.transactions
            if tx['sender'] == sender
        )
        available_balance = self.get_balance(sender) - pending_spends
        
        if sender != "node" and available_balance < quantity:
            print(colored(f"Transaction from {sender} to {recipient} for {quantity} rejected due to insufficient funds.", "red"))
            return {"status": False, "txid": None, "error": "Insufficient funds"}
        
        # Update balances
        if sender != "node":
            self.balances[sender] = self.balances.get(sender, 0) - totaltxspend
            self.balances[recipient] = self.balances.get(recipient, 0) + quantity
            
        # Create Transaction ID
        txid = self.calculate_txid(time.time(), len(self.chain))
        if sender == "node":
            fee = 0
        
        tx = {
            'sender': sender,
            'recipient': recipient,
            'quantity': quantity,
            'fee': fee, # Add fee to transaction
            'fee_percent': current_fee_percent,
            'txid': txid,
            'timestamp': time.time(),
        }
        
        try: 
            self.mempool.add_transaction(tx)
            #print(colored(f"Transaction from {sender} to {recipient} for {quantity} added to mempool.", "green")) #Debug
            return {"status": True, "txid": txid, "fee": fee}
        except MempoolFullError:
            return {"status": False, "txid": None, "error": "Mempool is full"}

    def proof_of_work(self , last_proof):
        '''this simple algorithm identifies a number f' such that hash(ff') contain 4 leading zeroes
         f is the previous f'
         f' is the new proof
        '''
        proofN = 0
        while self.verifying_proof(proofN, last_proof) is False:
            proofN += 1

        return proofN

    def verifying_proof(self, last_proof, proof, difficulty=None):
        """Modified to accept optional custom difficulty"""
        difficulty = difficulty or self.diff
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.blake2b(guess).hexdigest()

        if not guess_hash.startswith("0" * difficulty):
            #print(guess_hash)
            return False
        else:
            #print(guess_hash)
            return True

    @property
    def latest_block(self):
        return self.chain[-1]

    def block_mining(self, details_miner):

        self.new_data(
            sender="node",  #it implies that this node has created a new block
            recipient=details_miner,
            quantity=
            self.rewards,  #creating a new block (or identifying the proof number) is awarded with 1
        )

        last_block = self.latest_block

        last_proofN = last_block.proofN
        proofN = self.proof_of_work(last_proofN) # Soon it will be given by some random miner

        last_hash = last_block.calculate_hash
        block = self.construct_block(proofN, last_hash)
        self.balances[details_miner] = self.balances.get(details_miner, 0) + self.rewards

        return block
    
    def submit_mined_block(self, details_miner, proofN, last_hash):
        # Get the last block first
        last_block = self.latest_block
        
        # Update miner stats and get their current difficulty
        self.update_miner_stats(details_miner)
        current_diff = self.get_miner_difficulty(details_miner)
        
        # Verify with adjusted difficulty
        if not self.verifying_proof(last_block.proofN, proofN, current_diff):
            return ({
                "status": "error",
                "message": f"Proof doesn't meet required difficulty (needed: {current_diff})",
                "required_difficulty": current_diff,
                "your_difficulty_multiplier": self.miner_stats.get(details_miner, {}).get('multiplier', 1.0)
            }, 400)
            
        # Continue with block creation if proof is valid
        self.new_data(
            sender="node",
            recipient=details_miner,
            quantity=self.rewards
        )
        block = self.construct_block(proofN, last_hash)
        self.balances[details_miner] = self.balances.get(details_miner, 0) + self.rewards
        print(colored(f"\n-----------\nNew Block mined!\nHeight: {len(self.chain)}\nMiner: {details_miner}\nReward: {self.rewards} ZED \n-----------\n", "green"))
        return block

    def create_node(self, address):
        self.nodes.add(address)
        return True

    def get_balance(self, user):
        return self.balances.get(user, 0)
    
    def block_by_hash(self, block_hash):
        for block in self.chain:
            if block.calculate_hash == block_hash:
                return block
            
        return None
        # block = self.block_hash_map.get(block_hash, None)
        # if block:
        #     block.index = block.index
        #     if block.index+1 < len(self.chain):
        #         return self.chain[block.index+1] 
        
        # return None

    def format_hashrate(self, hashes_per_sec):
        # Format the hash rate into human-readable format
        units = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s"]
        unit_index = 0
        while hashes_per_sec >= 1000 and unit_index < len(units)-1:
            hashes_per_sec /= 1000
            unit_index += 1
        return f"{hashes_per_sec:.2f} {units[unit_index]}"

    @staticmethod
    def obtain_block_object(block_data):
        #obtains block object from the block data

        return Block(
            block_data['index'],
            block_data['proofN'],
            block_data['prev_hash'],
            block_data['transactions'],
            timestamp=block_data['timestamp'])
        
    def GetConfig(self):
        data = jsonify.load(open("src/data/config.json", "r"))
        return [data["address"], data["seed"]]

app = Sanic(__name__)
app.config.KEEP_ALIVE_TIMEOUT = 3600
blockchain = BlockChain()
blockchain.save_flag = True


####################### NODE ################################
@app.get("/ping")
@openapi.description("Ping the server")
async def pong(request):
    return json(
        {
            "result" : "pong!",
        }
    , 200)

####################### NETWORK #############################
@app.get("/network/info")
@openapi.description("Get network information")
async def get_network_info(request):
    return json({
        "height": len(blockchain.chain) - 1,
        "total_supply": blockchain.GetSupply(),
        "difficulty": blockchain.diff,
        "block_reward": blockchain.rewards,
        "node_count": len(blockchain.nodes),
        "threshold": blockchain.zedoguard_threshold,
        "window": blockchain.zedoguard_window,
        "zedoguard": blockchain.zedoguard,
    })

@app.get("/network/chain")
async def get_chain(request):
    chain_data = []
    for block in blockchain.chain:
        chain_data.append(block.__dict__)
    return json({"length": len(chain_data),
                       "chain": chain_data}, )

@app.get("/network/latestblock")
@openapi.description("Get the latest block")
async def get_block(request):
    return json(vars(blockchain.latest_block))

@app.get("/network/totalsupply")
@openapi.description("Get the total supply of the blockchain")
async def get_totalsupply(request):
    return json({
        "TotalSupply": blockchain.GetSupply()
    })
    
@app.get("/network/getblockbyhash/<hash>")
@openapi.description("Get block by hash")
def get_block_by_hash(request, hash):
    block = blockchain.block_by_hash(hash)
    print(block)
    if not(block):
        return json({
            "ERROR": f"{hash} not found"
        })
    else:
        return json(vars(block))

@app.get("/network/transactionbyid/<txid>")
@openapi.description("Get transaction by ID")
def get_transaction(request, txid):
    for block in blockchain.chain:
        for tx in block.transactions:
            if tx['txid'] == txid:
                return json({
                    "block_height": block.index,
                    "transaction": tx
                })
    return json({
        "ERROR": f"{txid} not found"
    }, 404)

@app.get("/network/transactions/<address>")
@openapi.description("Get all transactions for an address")
async def address_transactions(request, address):
    txs = []
    for block in blockchain.chain:
        for tx in block.transactions:
            if tx['sender'] == address or tx['recipient'] == address:
                tx_data = dict(tx)
                tx_data["block_height"] = block.index
                tx_data["timestamp"] = block.timestamp
                txs.append(tx_data)
    
    return json({"transactions": txs})

@app.get("/network/block/<blocknum>")
@openapi.description("Get block by number")
def get_block_by_num(request, blocknum : int):
    blockc = blockchain.chain
    if len(blockc) < blocknum:
        return json({
            "ERROR": "Block Doesnt Exist yet"
        }, 400)
    
    return json(vars(blockc[blocknum]))
    
@app.get("/network/blocks")
@openapi.description("Get blocks using ?count=<number>")
async def get_recent_blocks(request):
    count = int(request.args.get("count", 5))
    count = min(count, len(blockchain.chain))
    blocks = []
    
    for block in blockchain.chain[-count:]:
        blocks.append({
            "index": block.index,
            "hash": block.calculate_hash,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(block.timestamp)),
            "transactions": block.transactions,
            "proofN": block.proofN,
            "prev_hash": block.prev_hash
        })
    
    return json({"blocks": blocks[::-1]})  # Return newest first

@app.get("/network/transactions")
@openapi.description("Get transactions using ?count=<number>")
async def get_recent_transactions(request):
    count = int(request.args.get("count", 5))
    all_txs = []
    
    for block in reversed(blockchain.chain):
        for tx in reversed(block.transactions):
            tx_data = dict(tx)
            tx_data["block_height"] = block.index
            tx_data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(block.timestamp))
            all_txs.append(tx_data)
            if len(all_txs) >= count:
                break
        if len(all_txs) >= count:
            break
            
    return json({"transactions": all_txs})

@app.get("/network/hashrate")
async def get_network_hashrate(request):
    # Get current difficulty
    current_diff = blockchain.diff
    
    # Calculate average block time (last 60 blocks)
    block_count = min(60, len(blockchain.chain))
    if block_count < 2:
        return json({"error": "Need at least 2 blocks"}, status=400)
    
    oldest_block = blockchain.chain[-block_count]
    newest_block = blockchain.chain[-1]
    time_span = newest_block.timestamp - oldest_block.timestamp
    avg_block_time = time_span / (block_count - 1)
    
    # Calculate hashrate (fixed formula)
    # For leading zero difficulty: hashrate = (2^difficulty_bits) / avg_block_time
    # For blake2b (256-bit): hashrate = (2^256) / (2^(256-difficulty)) / block_time
    # Simplified to:
    hashrate = (2 ** current_diff) / avg_block_time
    
    return json({
        "hashrate": hashrate,
        "hashrate_human": blockchain.format_hashrate(hashrate),
        "difficulty": current_diff,
        "avg_block_time": avg_block_time,
        "blocks_analyzed": block_count
    })
    
# @app.get("/network/fee_info")
# @openapi.description("Get information about transaction fees")
# async def get_fee_info(request):
#     return json({
#         "fee_percentage": blockchain.mempool.get_current_fee_percent(),
#         "description": f"Fixed {round(blockchain.mempool.get_current_fee_percent()*100, 2)}% fee on all transactions",
#         "distribution": "Zedovium Development Fund",
#     })

@app.get("/network/fee_estimate")
@openapi.description("Get current fee estimate")
async def get_fee_estimate(request):
    current_fee = blockchain.mempool.get_current_fee_percent()
    mempool_status = {
        "fee": current_fee,
        "current_fee_percent": current_fee * 100,
        "mempool_utilization": f"{(len(blockchain.mempool.transactions)/blockchain.mempool.max_size)*100:.1f}%",
        "next_block_capacity": blockchain.mempool.block_tx_limit,
        "pending_transactions": len(blockchain.mempool.transactions),
        "total_fees": sum(tx['fee'] for tx in blockchain.mempool.transactions if 'fee' in tx) # Total fees in mempool
    }
    return json(mempool_status)

@app.get("/network/fee_chart")
@openapi.description("Visualize fee structure")
async def fee_chart(request):
    steps = 10
    data = []
    for i in range(steps + 1):
        utilization = i / steps
        temp_mempool = Mempool()  # Create temp instance for calculation
        temp_mempool.transactions = [None] * int(utilization * temp_mempool.max_size)
        fee = temp_mempool.get_current_fee_percent() * 100
        data.append({
            "mempool_utilization": f"{utilization*100:.0f}%",
            "fee_percent": fee
        })
    return json({"fee_structure": data})

@app.get("/network/checkaddrdiff/<address>")
@openapi.description("Check if an address is mining under normal or high difficulty")
async def check_address_difficulty(request, address):
    if not AddressGen.validate(address):
        return json({
            "status": "error",
            "message": "Invalid address format"
        }, status=400)
        
    # Check if address has mining stats
    if address in blockchain.miner_stats and blockchain.zedoguard:
        stats = blockchain.miner_stats[address]
        current_bph = len(stats['blocks'])
        if stats['multiplier'] > 1.0:
            status = "high"
            message = f"Address has high difficulty (mining {current_bph} blocks/hour)"
        else:
            status = "normal"
            message = f"Address has normal difficulty (mining {current_bph} blocks/hour)"
            
        return json({
            "status": status,
            "message": message,
            "difficulty_multiplier": stats['multiplier'],
            "current_blocks_per_hour": current_bph,
            "threshold": blockchain.zedoguard_threshold,
            "base_difficulty": blockchain.diff,
            "effective_difficulty": blockchain.get_miner_difficulty(address)
        })

    elif address not in blockchain.miner_stats and blockchain.zedoguard:
        return json({
            "status": "normal",
            "message": "Address has normal difficulty (no mining activity detected)",
            "difficulty_multiplier": 1.0,
            "current_blocks_per_hour": 0,
            "threshold": blockchain.zedoguard_threshold
        })
        
    elif address in blockchain.miner_stats and blockchain.zedoguard == False:
        stats = blockchain.miner_stats[address]
        current_bph = len(stats['blocks'])   
        return json({
            "status": "normal",
            "message": "Zedovium Guard is disabled. No difficulty checks.",
            "difficulty_multiplier": 0,
            "current_blocks_per_hour": current_bph,
            "threshold": blockchain.zedoguard_threshold,
            "base_difficulty": blockchain.diff,
            "effective_difficulty": blockchain.get_miner_difficulty(address)
        })
        
    elif address not in blockchain.miner_stats and blockchain.zedoguard == False:
        return json({
            "status": "normal",
            "message": "Zedovium Guard is disabled. No mining activity detected.",
            "difficulty_multiplier": 0,
            "current_blocks_per_hour": 0,
            "threshold": blockchain.zedoguard_threshold,
            "base_difficulty": blockchain.diff,
            "effective_difficulty": blockchain.get_miner_difficulty(address)
        })
        


####################### Mining ###################################

@app.get("/mining/info")
@openapi.description("Get mining information")
async def get_mining_info(request):
    return json ({
        "difficulty": blockchain.diff,
        "latestblock": vars(blockchain.latest_block)
        })
    
@app.post("/mining/submitblock")
@openapi.description("Submit a mined block")
async def submit_block(request):
    block_data = request.json
    index = block_data["index"]
    proofN = block_data['proofN']
    prev_hash = block_data['prev_hash']
    #transactions = block_data['transactions']
    miner_address = block_data['miner_address']
    timestamp = block_data['timestamp']
    
    last_block = blockchain.latest_block
    
    if last_block.index + 1 != index:
        return json({"message": "Invalid Index"}, 400)
    
    if last_block.calculate_hash != prev_hash:
        return json({"message":"Invalid previous hash"}, 400)
    
    if not blockchain.verifying_proof(last_block.proofN, proofN):
        return json({"message": "Invalid proof"}, 400)
    
    if timestamp <= last_block.timestamp:
        return json({"message": "Invalid timestamp"}, 400)
    
    block = blockchain.submit_mined_block(miner_address, proofN, prev_hash)
    try:
        return json(vars(block), 201)
    except Exception as e:
        if block[0]["status"] == "error":
            return json(block[0])

####################### USERS ####################################
@app.get("/user/balance/<address>")
@openapi.description("Get user balance")
async def get_balance(request, address):
    balance = blockchain.get_balance(address)
    return json({
        "Address": address,
        "Balance": balance
    })


######################### Wallet API #################################

@app.get("/wallet/create")
@openapi.description("Create a new wallet")
async def CreateWallet(request):
    wallet = AddressGen.generate()

    return json({
        "address": wallet['address'],
        "seed": wallet['seed'],
        "message": "Securely store your seed if you want to regenerate this address",
    })

@app.post("/wallet/import")
@openapi.description("Import an existing wallet")
# import an existing seed
async def ImportWallet(request):
    seed = request.json.get("seed", None)
    wallet = AddressGen.generate(seed)
    
    return json({
        "address": wallet['address'],
        "seed": wallet['seed']
    })

@app.get("/wallet/validate/<address>")
@openapi.description("Validate an address")
async def validate_address(request, address):
    return json({
        "address": address,
        "is_valid": AddressGen.validate(address)
    })

@app.post("/transaction/create")
@openapi.description("Create a new transaction and submit to mempool")
async def create_transaction(request):
    data = request.json
    sender = data.get('sender')
    recipient = data.get('recipient')
    amount = data.get('amount')
    seed = data.get('seed')
    
    if not all([sender, recipient, amount, seed]):
        return json({"status": False, "error": "Invalid Parameters"}, 400)
    
    try:
        amount = float(amount)
    except:
        return json({"status": False, "error": "Invalid Amount"}, 400)
    
    success = blockchain.new_transaction(sender, recipient, amount, seed)

    return json(success)



############################## Mempool API #################################
@app.get("/mempool/info")
@openapi.description("Get mempool information")
async def mempool_info(request):
    return json({
        "count": len(blockchain.mempool.transactions),
        "capacity": blockchain.mempool.max_size,
        "next_block_tx_count": min(
            len(blockchain.mempool.transactions),
            blockchain.mempool.block_tx_limit
        )
    })

@app.get("/mempool/transactions")
@openapi.description("Get transactions in mempool")
async def mempool_transactions(request):
    count = min(int(request.args.get("count", 100)), 1000)
    return json({
        "transactions": blockchain.mempool.transactions[:count]
    })
    

############################# Web3 Compat layer #############################
#for metamask very broken though

class Web3RPC:
    @staticmethod
    def zed_to_eth(address):
        """Convert ZED-address to 0x-format"""
        if address.startswith("ZED-"):
            # Take the first part of the ZED address and pad with zeros
            clean_hex = address.replace("ZED-", "").replace("-", "")[:40]
            return Web3.to_checksum_address("0x" + clean_hex.ljust(40, '0'))
        return address

    @staticmethod
    def eth_to_zed(address):
        """Convert 0x-address to ZED-format"""
        if address.startswith("0x"):
            clean_hex = address[2:]
            # Reconstruct ZED address format from the hex
            return f"ZED-{clean_hex[:8]}-{clean_hex[8:16]}-{clean_hex[16:24]}-{clean_hex[24:32]}"
        return address

    @staticmethod
    def to_hex(value):
        """Convert value to hex string"""
        if isinstance(value, str) and value.startswith("0x"):
            return value
        return hex(int(value))

    @staticmethod
    def handle_web3_request(method, params):
        """Handle Web3 JSON-RPC methods"""
        try:
            if method == "eth_chainId":
                return Web3RPC.to_hex(blockchain.CHAIN_ID)
            
            elif method == "net_version":
                return Web3RPC.to_hex(blockchain.CHAIN_ID)
            
            elif method == "eth_blockNumber":
                latest_block = blockchain.latest_block
                return Web3RPC.to_hex(latest_block.index)
            
            elif method == "eth_getBalance":
                if len(params) < 2:
                    raise ValueError("Missing parameters")
                address = Web3RPC.eth_to_zed(params[0])
                balance = blockchain.get_balance(address)
                return Web3RPC.to_hex(int(balance * (10 ** blockchain.DECIMAL)))
            
            elif method == "eth_getTransactionCount":
                if len(params) < 2:
                    raise ValueError("Missing parameters")
                address = Web3RPC.eth_to_zed(params[0])
                # In your system, we'll use the number of outgoing transactions as nonce
                # This is a simplification - you might need to track nonces properly
                count = 0
                for block in blockchain.chain:
                    for tx in block.transactions:
                        if tx['sender'] == address:
                            count += 1
                return Web3RPC.to_hex(count)
            
            elif method == "eth_getBlockByNumber":
                if len(params) < 2:
                    raise ValueError("Missing parameters")
                
                block_num = params[0]
                full_tx = params[1]
                
                if block_num == "latest":
                    block = blockchain.latest_block
                elif block_num == "earliest":
                    block = blockchain.chain[0]
                else:
                    try:
                        block_num = int(block_num, 16) if isinstance(block_num, str) and block_num.startswith("0x") else int(block_num)
                        if block_num >= len(blockchain.chain):
                            return None
                        block = blockchain.chain[block_num]
                    except:
                        return None
                
                # Convert transactions based on full_tx flag
                transactions = []
                if full_tx:
                    for tx in block.transactions:
                        transactions.append({
                            "hash": tx.get('txid', '0x' + secrets.token_hex(32)),
                            "from": Web3RPC.zed_to_eth(tx['sender']),
                            "to": Web3RPC.zed_to_eth(tx['recipient']),
                            "value": Web3RPC.to_hex(int(tx['quantity'] * (10 ** blockchain.DECIMAL))),
                            "gas": Web3RPC.to_hex(21000),  # Standard gas for simple transfer
                            "gasPrice": Web3RPC.to_hex(1),  # Minimal gas price
                            "nonce": Web3RPC.to_hex(0),     # Would need proper nonce tracking
                            "blockHash": "0x" + block.calculate_hash,
                            "blockNumber": Web3RPC.to_hex(block.index),
                            "transactionIndex": Web3RPC.to_hex(0)
                        })
                else:
                    transactions = [tx.get('txid', '0x' + secrets.token_hex(32)) for tx in block.transactions]
                
                return {
                    "number": Web3RPC.to_hex(block.index),
                    "hash": "0x" + block.calculate_hash,
                    "parentHash": "0x" + block.prev_hash if block.prev_hash != "0" else "0x" + "0"*64,
                    "nonce": "0x" + "0"*16,
                    "sha3Uncles": "0x" + "0"*64,
                    "logsBloom": "0x" + "0"*512,
                    "transactionsRoot": "0x" + "0"*64,
                    "stateRoot": "0x" + "0"*64,
                    "miner": Web3RPC.zed_to_eth("node"),  # Your system uses "node" as miner
                    "difficulty": Web3RPC.to_hex(blockchain.diff),
                    "totalDifficulty": Web3RPC.to_hex(blockchain.diff * (block.index + 1)),
                    "extraData": "0x",
                    "size": Web3RPC.to_hex(1000),  # Approximate
                    "gasLimit": Web3RPC.to_hex(8000000),  # Standard gas limit
                    "gasUsed": Web3RPC.to_hex(21000 * len(block.transactions)),
                    "timestamp": Web3RPC.to_hex(int(block.timestamp)),
                    "transactions": transactions,
                    "uncles": []
                }
            
            elif method == "eth_sendTransaction":
                if len(params) < 1:
                    raise ValueError("Missing parameters")
                
                tx_data = params[0]
                sender = Web3RPC.eth_to_zed(tx_data.get('from'))
                recipient = Web3RPC.eth_to_zed(tx_data.get('to'))
                value = int(tx_data.get('value', '0x0'), 16) / (10 ** blockchain.DECIMAL)
                
                # In a real implementation, you'd need to:
                # 1. Verify the signature (your system currently uses seed)
                # 2. Handle nonce properly
                # For now, we'll just create a transaction (insecure - for demo only)
                
                # This is a major limitation - your system needs to support signed transactions
                # without requiring the seed to be sent to the server
                return {"error": "eth_sendTransaction not fully implemented - use eth_sendRawTransaction with proper signing"}
            
            elif method == "eth_sendRawTransaction":
                # This would need proper transaction signing implementation
                return {"error": "eth_sendRawTransaction not implemented"}
            
            elif method == "eth_gasPrice":
                return Web3RPC.to_hex(1)  # Minimal gas price
            
            elif method == "eth_estimateGas":
                return Web3RPC.to_hex(21000)  # Standard gas for simple transfer
            
            elif method == "eth_call":
                # For contract calls - your system doesn't support contracts yet
                return "0x"
            
            else:
                raise ValueError(f"Unsupported method: {method}")
        
        except Exception as e:
            return {"error": str(e)}

@app.post("/web3")
async def handleWeb3Request(request):
    try:
        data = request.json
        if isinstance(data, dict):
            # Single request
            method = data.get("method")
            params = data.get("params", [])
            id = data.get("id", 1)
            
            result = Web3RPC.handle_web3_request(method, params)
            
            if isinstance(result, dict) and "error" in result:
                return json({
                    "jsonrpc": "2.0",
                    "id": id,
                    "error": {
                        "code": -32602,
                        "message": result["error"]
                    }
                })
            else:
                return json({
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": result
                })
        
        elif isinstance(data, list):
            # Batch request
            responses = []
            for item in data:
                method = item.get("method")
                params = item.get("params", [])
                id = item.get("id", 1)
                
                result = Web3RPC.handle_web3_request(method, params)
                
                if isinstance(result, dict) and "error" in result:
                    responses.append({
                        "jsonrpc": "2.0",
                        "id": id,
                        "error": {
                            "code": -32602,
                            "message": result["error"]
                        }
                    })
                else:
                    responses.append({
                        "jsonrpc": "2.0",
                        "id": id,
                        "result": result
                    })
            
            return json(responses)
        
        else:
            return json({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32600,
                    "message": "Invalid Request"
                }
            }, status=400)
    
    except Exception as e:
        return json({
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }, status=500)

# Add these routes to your Sanic app
@app.route("/openapi.json")
async def serve_openapi_spec(request):
    # Load your custom OpenAPI spec
    with open(os.path.join(os.path.dirname(__file__), "openapi.json"), "r") as f:
        spec = jsonify.load(f)
    return json(spec)

def greeter():
    if os.path.exists("src/data/config.json"):
        data = jsonify.load(open("src/data/config.json", "r"))
        address = AddressGen.validate(data["address"])
        if address:
            print(colored(f"Welcome back {data['address']}!", "green"))
        else:
            print(colored("Invalid address in config.json :( ignoring", "red"))
    else:
        pass

if __name__ == "__main__":
    greeter()
    app.run(debug=True, port=4024, single_process=True)
