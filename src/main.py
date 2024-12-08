"""
    main.py handles the core blockchain
    Copyright (C) 2024 Babymusk

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

"""


from hashlib import blake2b
import json as jsonify
import time

from sanic import Sanic
from sanic.response import text, json
import requests, pprint, os, signal, sys
from termcolor import colored
from ecdsa import SigningKey, VerifyingKey, SECP256k1


import hashlib
import time


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
        
        self.totalsupply = sum(list(self.balances.values()))
        self.block_hash_map = {block.calculate_hash: block for block in self.chain}
        
        
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
            
    def SaveDB(self):
        with open("src/data/blockchain.json", "w") as f:
            Tosave = [block.to_dict() for block in self.chain]
            jsonify.dump(Tosave, f)
            #print(Tosave)
            f.close()
            
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
        block = Block(
            index=len(self.chain),
            proofN=proofN,
            prev_hash=prev_hash,
            transactions=self.current_transactions)
        self.current_transactions = []

        self.chain.append(block)
        self.block_hash_map[block.calculate_hash] = block  # Add to hash map
        if self.save_flag:
            self.SaveDB()
        
        self.adjust_difficulty()  # Adjust difficulty after adding a new block

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

    def new_data(self, sender, recipient, quantity):
        if sender != "node" and self.balances.get(sender, 0) < quantity:
            print(colored(f"Transaction from {sender} to {recipient} for {quantity} rejected due to insufficient funds.", "red"))
            return False
        
        # Update balances
        if sender != "node":
            self.balances[sender] = self.balances.get(sender, 0) - quantity
            self.balances[recipient] = self.balances.get(recipient, 0) + quantity
            
        # Create Transaction ID
        txid = self.calculate_txid(time.time(), len(self.chain))
        
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'quantity': quantity,
            'txid': txid
        })
        return True

    def proof_of_work(self , last_proof):
        '''this simple algorithm identifies a number f' such that hash(ff') contain 4 leading zeroes
         f is the previous f'
         f' is the new proof
        '''
        proofN = 0
        while self.verifying_proof(proofN, last_proof) is False:
            proofN += 1

        return proofN

    def verifying_proof(self, last_proof, proof):
        #verifying the proof: does hash(last_proof, proof) contain 4 leading zeroes?

        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.blake2b(guess).hexdigest()
        if not guess_hash.startswith("0" * self.diff):
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
        # for block in self.chain:
        #     if block.calculate_hash == block_hash:
        #         return block
            
        # return None
        block = self.block_hash_map.get(block_hash, None)
        if block:
            block.index = block.index
            if block.index+1 < len(self.chain):
                return self.chain[block.index+1] 
        
        return None               

    @staticmethod
    def obtain_block_object(block_data):
        #obtains block object from the block data

        return Block(
            block_data['index'],
            block_data['proofN'],
            block_data['prev_hash'],
            block_data['transactions'],
            timestamp=block_data['timestamp'])


app = Sanic(__name__)
app.config.KEEP_ALIVE_TIMEOUT = 3600

blockchain = BlockChain()
blockchain.save_flag = True

blockchain.new_data(
    "miner1",
    "miner2",
    10
)

####################### NODE ################################
@app.get("/ping")
async def pong(request):
    return json(
        {
            "result" : "pong!",
        }
    , 200)

####################### NETWORK #############################
@app.get("/network/chain")
async def get_chain(request):
    chain_data = []
    for block in blockchain.chain:
        chain_data.append(block.__dict__)
    return json({"length": len(chain_data),
                       "chain": chain_data}, )

@app.get("/network/latestblock")
async def get_block(request):
    return json(vars(blockchain.latest_block))

@app.get("/network/totalsupply")
async def get_totalsupply(request):
    return json({
        "TotalSupply": blockchain.totalsupply
    })
    
@app.get("/network/getblockbyhash/<hash>")
def get_block_by_hash(request, hash):
    block = blockchain.block_by_hash(hash)
    print(block)
    if not(block):
        return json({
            "ERROR": f"{hash} not found"
        })
    else:
        return json(vars(block))

@app.get("/network/block/<blocknum>")
def get_block_by_num(request, blocknum : int):
    blockc = blockchain.chain
    if len(blockc) < blocknum:
        return json({
            "ERROR": "Block Doesnt Exist yet"
        }, 400)
    
    return json(vars(blockc[blocknum]))
    
####################### Mining ###################################

@app.get("/mining/info")
async def get_mining_info(request):
    return json ({
        "difficulty": blockchain.diff,
        "latestblock": vars(blockchain.latest_block)
        })
    
@app.post("/mining/submitblock")
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
    
    return json(vars(block), 201)


####################### USERS ####################################
@app.get("/user/balance/<address>")
async def get_balance(request, address):
    balance = blockchain.get_balance(address)
    return json({
        "Address": address,
        "Balance": balance
    })


if __name__ == "__main__":
    app.run(debug=True, port=4024, single_process=True)
