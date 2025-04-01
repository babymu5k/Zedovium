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
