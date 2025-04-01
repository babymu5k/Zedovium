import hashlib
import secrets

class AddressGen:
    """Address Generation for ZED"""
    def __init__(self, wordlist):
        self.WORDLIST = wordlist
    
    #@staticmethod
    def generate(self, seed=None):
        """Create a beautiful deterministic address"""
        seed = seed or secrets.token_hex(16)  # 16 random bytes if no seed
        
        # Hash the seed
        seed_hash = hashlib.sha256(seed.encode()).digest()
        # Convert to 4 words
        word_indices = [
            int.from_bytes(seed_hash[i:i+2], 'big') % len(self.WORDLIST)
            for i in range(0, 8, 2)
        ]
        words = [self.WORDLIST[i] for i in word_indices]
        
        # Generate checksum (first 4 chars of hash)
        phrase = "-".join(words)
        checksum = hashlib.sha256(phrase.encode()).hexdigest()[:4]
        
        return {
            "address": f"ZED-{phrase}-{checksum}",
            "seed": seed,  # Keep this secret!
        }

    #@staticmethod
    def validate(self, address):
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

    #@staticmethod
    def verify_ownership(self, claimed_address, seed):
        """Verify that seed generates the claimed address"""
        generated_address = self.generate(seed)["address"]
        return generated_address == claimed_address