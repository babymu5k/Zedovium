# wallet_cli.py - The standalone wallet CLI
import cmd
import sys
import json, hashlib
import getpass
import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter

class ZEDWalletCLI(cmd.Cmd):
    """Command-line wallet interface for ZED cryptocurrency"""
    
    prompt = ">>> "
    NODE_URL = "http://localhost:4024"
    
    def __init__(self):
        super().__init__()
        self.current_wallet = None
        self.session = PromptSession(
            history=FileHistory('.zed_history'),
            auto_suggest=AutoSuggestFromHistory()
        )
        
        # Set up command completer
        self.commands = [
            'new', 'load', 'balance', 'send', 'exit', 
            'help', 'info', 'address', 'connect',
            'blocks', 'transactions'
        ]
        self.completer = WordCompleter(self.commands)
        
        print("\nZED Cryptocurrency Wallet - Command Line Interface")
        print("""
#######                                             
     #  ###### #####   ####  #    # # #    # #    # 
    #   #      #    # #    # #    # # #    # ##  ## 
   #    #####  #    # #    # #    # # #    # # ## # 
  #     #      #    # #    # #    # # #    # #    # 
 #      #      #    # #    #  #  #  # #    # #    # 
####### ###### #####   ####    ##   #  ####  #    # v0.1.0                                         
              """)
        print(f"Connected to node: {self.NODE_URL}")
        print("Type 'help' for available commands\n")

    def cmdloop(self, intro=None):
        while True:
            try:
                user_input = self.session.prompt(self.prompt, completer=self.completer)
                self.onecmd(user_input)
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit")
            except EOFError:
                self.do_exit(None)
                break
            except Exception as e:
                print(f"Error: {e}")

    def do_connect(self, arg):
        """Connect to a different node: connect [url]"""
        if arg:
            self.NODE_URL = arg.rstrip('/')
            print(f"\nConnected to node: {self.NODE_URL}\n")
        else:
            print(f"\nCurrently connected to: {self.NODE_URL}\n")

    def do_new(self, arg):
        """Create a new wallet: new"""
        try:
            response = requests.get(f"{self.NODE_URL}/wallet/create")
            if response.status_code == 200:
                wallet = response.json()
                self.current_wallet = wallet
                print("\n=== New Wallet Created ===")
                print(f"Address: {wallet['address']}")
                print(f"Seed: {wallet['seed']}")
                print("\nIMPORTANT: Save this seed phrase securely!")
                print("If you lose it, you will lose access to your funds.\n")
            else:
                print(f"\nError creating wallet: {response.text}\n")
        except requests.exceptions.RequestException as e:
            print(f"\nConnection error: {e}\n")

    def do_load(self, arg):
        """Load an existing wallet: load [seed]"""
        if not arg:
            seed = getpass.getpass("Enter seed phrase: ")
        else:
            seed = arg.strip()
        
        try:
            response = requests.post(
                f"{self.NODE_URL}/wallet/import",
                json={"seed": seed}
            )
            
            if response.status_code == 200:
                wallet = response.json()
                self.current_wallet = wallet
                balance = self._get_balance(wallet['address'])
                print("\n=== Wallet Loaded ===")
                print(f"Address: {wallet['address']}")
                print(f"Balance: {balance} ZED\n")
            else:
                print(f"\nError loading wallet: {response.text}\n")
        except requests.exceptions.RequestException as e:
            print(f"\nConnection error: {e}\n")

    def _get_balance(self, address):
        """Helper method to get balance"""
        try:
            response = requests.get(f"{self.NODE_URL}/user/balance/{address}")
            if response.status_code == 200:
                return response.json().get('Balance', 0)
            return 0
        except requests.exceptions.RequestException:
            return 0

    def do_balance(self, arg):
        """Check wallet balance: balance"""
        if not self.current_wallet:
            print("No wallet loaded. Use 'new' or 'load' first.")
            return
            
        balance = self._get_balance(self.current_wallet['address'])
        print(f"\nBalance: {balance} ZED\n")

    def do_send(self, arg):
        """Send ZED to another address: send [amount] [recipient]"""
        if not self.current_wallet:
            print("No wallet loaded. Use 'new' or 'load' first.")
            return
            
        args = arg.split()
        if len(args) < 2:
            print("Usage: send [amount] [recipient]")
            return
            
        try:
            amount = float(args[0])
            recipient = args[1]
            
            # Validate recipient address
            if self.validate(recipient) == False:
                print("Invalid recipient address")
                return
                
            # Verify sufficient balance
            balance = self._get_balance(self.current_wallet['address'])
            if balance < amount:
                print(f"Insufficient balance. You have {balance} ZED")
                return
                
            # Confirm transaction
            print(f"\nSending {amount} ZED to {recipient}")
            confirm = input("Confirm? (y/n): ").lower()
            if confirm != 'y':
                print("Transaction canceled")
                return
                
            # Send transaction
            response = requests.post(
                f"{self.NODE_URL}/transaction/create",
                json={
                    'sender': self.current_wallet['address'],
                    'recipient': recipient,
                    'amount': amount,
                    'seed': self.current_wallet['seed']
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status'):
                    print(f"\nTransaction successful! TXID: {result.get('txid', 'N/A')}\n")
                else:
                    print(f"\nTransaction failed: {result.get('error', 'Unknown error')}\n")
            else:
                print(f"\nTransaction failed: {response.text}\n")
                
        except ValueError:
            print("Invalid amount")
        except requests.exceptions.RequestException as e:
            print(f"\nConnection error: {e}\n")

    def do_address(self, arg):
        """Show current wallet address: address"""
        if not self.current_wallet:
            print("No wallet loaded. Use 'new' or 'load' first.")
            return
            
        print(f"\nCurrent wallet address: {self.current_wallet['address']}\n")

    def do_info(self, arg):
        """Show blockchain info: info"""
        try:
            response = requests.get(f"{self.NODE_URL}/network/info")
            if response.status_code == 200:
                data = response.json()
                print("\n=== Blockchain Info ===")
                print(f"Current height: {data.get('height', 'N/A')}")
                print(f"Total supply: {data.get('total_supply', 'N/A')} ZED")
                print(f"Current difficulty: {data.get('difficulty', 'N/A')}")
                print(f"Block reward: {data.get('block_reward', 'N/A')} ZED")
                print(f"Connected nodes: {data.get('node_count', 'N/A')}\n")
            else:
                print(f"\nError getting info: {response.text}\n")
        except requests.exceptions.RequestException as e:
            print(f"\nConnection error: {e}\n")

    def do_blocks(self, arg):
        """Show recent blocks: blocks [count]"""
        try:
            count = int(arg) if arg else 5
            response = requests.get(f"{self.NODE_URL}/network/blocks?count={count}")
            
            if response.status_code == 200:
                blocks = response.json().get('blocks', [])
                print(f"\nLast {len(blocks)} blocks:")
                print("-" * 80)
                
                for block in blocks:
                    print(f"Height: {block.get('index', 'N/A')}")
                    print(f"Hash: {block.get('hash', 'N/A')}")
                    print(f"Timestamp: {block.get('timestamp', 'N/A')}")
                    print(f"Transactions: {len(block.get('transactions', []))}")
                    print("-" * 80)
                    
                print()
            else:
                print(f"\nError getting blocks: {response.text}\n")
        except ValueError:
            print("Invalid block count")
        except requests.exceptions.RequestException as e:
            print(f"\nConnection error: {e}\n")

    def do_transactions(self, arg):
        """Show recent transactions: transactions [count]"""
        try:
            count = int(arg) if arg else 5
            response = requests.get(f"{self.NODE_URL}/network/transactions?count={count}")
            
            if response.status_code == 200:
                transactions = response.json().get('transactions', [])
                print(f"\nLast {len(transactions)} transactions:")
                print("-" * 80)
                
                for tx in transactions:
                    print(f"TXID: {tx.get('txid', 'N/A')}")
                    print(f"Block: {tx.get('block_height', 'N/A')}")
                    print(f"From: {tx.get('sender', 'N/A')}")
                    print(f"To: {tx.get('recipient', 'N/A')}")
                    print(f"Amount: {tx.get('quantity', 'N/A')} ZED")
                    print(f"Timestamp: {tx.get('timestamp', 'N/A')}")
                    print("-" * 80)
                    
                print()
            else:
                print(f"\nError getting transactions: {response.text}\n")
        except ValueError:
            print("Invalid transaction count")
        except requests.exceptions.RequestException as e:
            print(f"\nConnection error: {e}\n")

    def do_exit(self, arg):
        """Exit the CLI: exit"""
        print("\nGoodbye!\n")
        sys.exit(0)

    def emptyline(self):
        pass

    def default(self, line):
        print(f"Unknown command: {line}")
        print("Type 'help' for available commands")

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


if __name__ == "__main__":
    wallet = ZEDWalletCLI()
    wallet.cmdloop()