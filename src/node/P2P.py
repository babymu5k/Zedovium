# To be implemented

import time
import ujson
import requests
from termcolor import colored
from collections import defaultdict
import random, threading

class P2PNetwork:
    def __init__(self, blockchain, initial_peers=None):
        self.blockchain = blockchain
        self.peers = set(initial_peers) if initial_peers else set()
        self.connected_peers = set()
        self.peer_lock = threading.Lock()
        
    def discover_peers(self):
        """Discover new peers by asking existing peers"""
        new_peers = set()
        
        with self.peer_lock:
            current_peers = list(self.peers)
            
        for peer in current_peers:
            try:
                response = requests.get(f"http://{peer}/network/peers", timeout=5)
                if response.status_code == 200:
                    peer_list = response.json().get('peers', [])
                    new_peers.update(peer_list)
            except:
                continue
                
        # Add new peers (with some limits to prevent spam)
        with self.peer_lock:
            self.peers.update(new_peers)
            # Keep peer list manageable
            if len(self.peers) > 100:
                self.peers = set(list(self.peers)[:100])
                
        return len(new_peers)
    
    def maintain_connections(self):
        """Maintain active connections to peers"""
        with self.peer_lock:
            to_remove = set()
            for peer in self.connected_peers:
                try:
                    requests.get(f"http://{peer}/ping", timeout=3)
                except:
                    to_remove.add(peer)
                    
            self.connected_peers -= to_remove
            
            # Try to connect to new peers if we're below target
            target_connections = 8
            if len(self.connected_peers) < target_connections:
                available = self.peers - self.connected_peers
                for peer in list(available)[:target_connections - len(self.connected_peers)]:
                    try:
                        requests.get(f"http://{peer}/ping", timeout=3)
                        self.connected_peers.add(peer)
                    except:
                        continue