# wallet_cli.py - The standalone wallet CLI
import cmd
import sys
import json, hashlib
import os, time, random, datetime
import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from termcolor import colored


class ZEDWalletCLI(cmd.Cmd):
    """Command-line wallet interface for ZED cryptocurrency"""

    prompt = ">>> "

    def __init__(self):
        super().__init__()
        self.current_wallet = None
        self.session = PromptSession(
            history=FileHistory(".zed_history"), auto_suggest=AutoSuggestFromHistory()
        )

        # Set up command completer
        self.commands = [
            "new",
            "load",
            "balance",
            "send",
            "exit",
            "help",
            "info",
            "address",
            "connect",
            "blocks",
            "transactions",
            "blocktime",
            "unconfirmed",
            "zedoguard",
            "estimate"
        ]
        self.completer = WordCompleter(self.commands)
        self.NODE_URL = self.getnode()
        self.clear_screen()
        print("\nZED Cryptocurrency Wallet - Command Line Interface")
        print(
            """
#######                                             
     #  ###### #####   ####  #    # # #    # #    # 
    #   #      #    # #    # #    # # #    # ##  ## 
   #    #####  #    # #    # #    # # #    # # ## # 
  #     #      #    # #    # #    # # #    # #    # 
 #      #      #    # #    #  #  #  # #    # #    # 
####### ###### #####   ####    ##   #  ####  #    # v0.1.0                                         
              """
        )
        print(colored(f"Connected to node: {self.NODE_URL}", "blue"))
        print("Type 'help' for available commands\n")
        self.do_load("1")

    def clear_screen(self):
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

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
            try:
                requests.get(f"{arg}/ping").status_code == 200
                self.NODE_URL = arg.rstrip("/")
                print(colored(f"\nConnected to node: {self.NODE_URL}\n", "green"))

            except requests.exceptions.RequestException:
                print(
                    colored(
                        f"\nFailed to connect to node: {arg}\nRemaining on: {self.NODE_URL}\n",
                        "red",
                    )
                )

        else:
            print(colored(f"\nCurrently connected to: {self.NODE_URL}\n", "blue"))

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
                # Save wallet details to a JSON file
                wallet_data = {"address": wallet["address"], "seed": wallet["seed"]}
                with open("src/data/config.json", "w") as wallet_file:
                    json.dump(wallet_data, wallet_file, indent=4)
                print("Wallet details saved to 'src/data/config.json'")
            else:
                print(f"\nError creating wallet: {response.text}\n")
        except requests.exceptions.RequestException as e:
            print(f"\nConnection error: {e}\n")

    def do_load(self, arg):
        """Load an existing wallet: load"""

        if not os.path.exists("src/data/config.json"):
            print("No wallet found. Create a new wallet first.")
            return
        with open("src/data/config.json", "r") as wallet_file:
            try:
                wallet_data = json.load(wallet_file)
            except json.JSONDecodeError:
                print("Error reading wallet file. Please check the file.")
                return
        if "address" not in wallet_data or "seed" not in wallet_data:
            print("Invalid wallet data. Please create a new wallet.")
        else:
            self.current_wallet = wallet_data
            print("\n=== Wallet Loaded ===")
            print(f"Address: {wallet_data['address']}")

            try:
                balance = self._get_balance(wallet_data["address"])
            except requests.exceptions.RequestException as e:
                print(f"\nConnection error: {e}\n")
                return

            print(f"Balance: {balance} ZED\n")

    def _get_balance(self, address):
        """Helper method to get balance"""
        try:
            response = requests.get(f"{self.NODE_URL}/user/balance/{address}")
            if response.status_code == 200:
                return response.json().get("Balance", 0)
            return 0
        except requests.exceptions.RequestException as e:
            return e

    def do_balance(self, arg):
        """Check wallet balance: balance [address]"""

        if not self.current_wallet:
            if not arg:
                print("No wallet loaded. Use 'new' or 'load' first.")
                return

        else:
            address = arg if arg else self.current_wallet["address"]

        balance = self._get_balance(address)
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
            balance = self._get_balance(self.current_wallet["address"])
            if balance < amount:
                print(f"Insufficient balance. You have {balance} ZED")
                return

            # Confirm transaction
            print(f"\nSending {amount} ZED to {recipient}")
            confirm = input("Confirm? (y/n): ").lower()
            if confirm != "y":
                print("Transaction canceled")
                return

            # Send transaction
            response = requests.post(
                f"{self.NODE_URL}/transaction/create",
                json={
                    "sender": self.current_wallet["address"],
                    "recipient": recipient,
                    "amount": amount,
                    "seed": self.current_wallet["seed"],
                },
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("status"):
                    print(
                        f"\nTransaction successful! TXID: {result.get('txid', 'N/A')} it should confirm soon!\n"
                    )
                else:
                    print(
                        f"\nTransaction failed: {result.get('error', 'Unknown error')}\n"
                    )
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
                nethashrate = requests.get(f"{self.NODE_URL}/network/hashrate").json()[
                    "hashrate_human"
                ]
                data = response.json()
                print("\n=== Blockchain Info ===")
                print(f"Current height: {data.get('height', 'N/A')}")
                print(f"Total supply: {data.get('total_supply', 'N/A')} ZED")
                print(f"Current difficulty: {data.get('difficulty', 'N/A')}")
                print(f"Block reward: {data.get('block_reward', 'N/A')} ZED")
                print(f"Network Hashrate: {nethashrate}")
                print(f"Connected nodes: {data.get('node_count', 'N/A')}")
                print(f"ZedoGuard Threshold: {data.get('threshold', 'N/A')} blocks")
                print(f"ZedoGuard Window: {data.get('window', 'N/A')} seconds")
                if data.get("zedoguard"):
                    print(f"ZedoGuard Status: {data.get('zedoguard', 'N/A')}")
                else:
                    pass
                print("-" * 29 + "\n")

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
                blocks = response.json().get("blocks", [])
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
        """Show recent transactions regarding this address: transactions [count]"""
        count = int(arg) if arg else 3
        try:
            response = requests.get(
                f"{self.NODE_URL}/network/transactions/{self.current_wallet['address']}"
            )

            if response.status_code == 200:
                transactions = response.json().get("transactions", [])
                print(f"\nLast {len(transactions[-count:])} transactions:")
                print("-" * 80)

                for tx in transactions[-count:]:
                    print(f"TXID: {tx.get('txid', 'N/A')}")
                    print(f"Block: {tx.get('block_height', 'N/A')}")
                    if tx.get("sender") == self.current_wallet["address"]:
                        print(colored(f"From: {tx.get('sender', 'N/A')} (you)", "blue"))
                    else:
                        print(f"From: {tx.get('sender', 'N/A')}")
                    if tx.get("recipient") == self.current_wallet["address"]:
                        print(
                            colored(f"To: {tx.get('recipient', 'N/A')} (you)", "blue")
                        )
                    else:
                        print(f"To: {tx.get('recipient', 'N/A')}")
                    print(f"Amount: {tx.get('quantity', 'N/A')} ZED")
                    print(f"Fee: {round(tx.get('fee', 'N/A'), 3)} ZED")
                    # print(f"Timestamp: {tx.get('timestamp', 'N/A')}")
                    print(
                        f"Timestamp: {datetime.datetime.fromtimestamp(tx.get('timestamp', 'N/A')):%Y-%m-%d %H:%M:%S} ({tx.get('timestamp', 'N/A')})"
                    )
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

    def do_blocktime(self, arg):
        """Show time since last block: blocktime"""
        latestblock = requests.get(f"{self.NODE_URL}/network/latestblock").json()[
            "timestamp"
        ]
        timenow = time.time()
        elapsed = timenow - latestblock
        elapsed_pretty = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        if elapsed <= 30:
            print("\nLast block was found just now.\n")
        elif elapsed < 240:
            print(f"\nLast block was found {int(elapsed)} seconds ago.\n")
        elif elapsed < 3600:
            minutes = int(elapsed // 60)
            if minutes == 1:
                print(f"\nLast block was found {minutes} minute ago.\n")
            else:
                print(f"\nLast block was found {minutes} minutes ago.\n")
        else:
            print(f"\nLast block was found {elapsed_pretty} ago.\n")

    def do_unconfirmed(self, arg):
        """Show unconfirmed transactions: unconfirmed"""
        mempool = requests.get(f"{self.NODE_URL}/mempool/transactions").json()
        print(colored(f"\nUnconfirmed transaction:", "blue"))
        print("-" * 80)
        for transaction in mempool["transactions"]:
            if (
                transaction["sender"] == self.current_wallet["address"]
                or transaction["recipient"] == self.current_wallet["address"]
            ):
                print(f"TXID: {transaction['txid']}")
                print(f"From: {transaction['sender']}")
                print(f"To: {transaction['recipient']}")
                print(f"Amount: {transaction['quantity']} ZED")
                print(f"Fee: {round(transaction['fee'], 4)} ZED")
                print(
                    f"Timestamp: {datetime.datetime.fromtimestamp(transaction['timestamp']):%Y-%m-%d %H:%M:%S} ({transaction['timestamp']})"
                )
                print("-" * 80)

    def do_zedoguard(self, arg):
        """Check if you miner is going too fast and has been throttled by Zedoguard: zedoguard"""
        response = requests.get(
            f"{self.NODE_URL}/network/checkaddrdiff/{self.current_wallet['address']}"
        ).json()

        if (
            response["current_blocks_per_hour"] > response["threshold"]
            and response["status"] == "high"
        ):
            print(colored(f"\n⚠ WARNING: Your miner is running too fast!\n", "red"))
            print(
                colored(
                    f"Current difficulty for your miner: {response['effective_difficulty']}",
                    "yellow",
                )
            )
            print(colored(f"{response['message']}\n", "yellow"))

        elif (
            response["current_blocks_per_hour"] <= response["threshold"]
            and response["status"] == "normal"
        ):
            print(colored(f"\nYour miner is running at a normal speed.\n", "green"))

        elif response["current_blocks_per_hour"] == 0:
            print(colored(f"\nYour miner is not mining at all.\n", "red"))

    def do_estimate(self, arg):
        """Estimate the fee for a transaction: estimate [amount]"""
        fee_percent = requests.get(f"{self.NODE_URL}/network/fee_estimate").json()
        fee = fee_percent["fee"]
        fee_percentage = fee_percent["current_fee_percent"]
        if arg:
            try:
                amount = float(arg)
                if amount <= 0:
                    print("Amount must be greater than 0")
                    return
                estimated_fee = amount * fee
                txamount = amount + estimated_fee
                print(colored(f"\nTotal transaction amount: {txamount} ZED", "blue"))
                print(f"\nCurrent fee: {fee} ZED")
                print(f"Estimated fee: {estimated_fee} ZED")
                print(f"Fee percentage: {fee_percentage}%")
                print(f"Mempool utilization: {fee_percent['mempool_utilization']}")
                print(f"Total Fees in Mempool: {fee_percent['total_fees']} ZED")
                
            except ValueError:
                print("Invalid amount")
                return
        
        if not arg:
            print(f"Current fee: {fee} ZED")
            print(f"Fee percentage: {fee_percentage}%")
            print(f"Mempool utilization: {fee_percent['mempool_utilization']}")
            print(f"Total Fees in Mempool: {fee_percent['total_fees']} ZED")
            return

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

    def getnode(self):
        response = requests.get(
            "https://raw.githubusercontent.com/babymu5k/Zedovium/refs/heads/develop/nodelist.json"
        ).json()
        return random.choice(response["nodes"])


if __name__ == "__main__":
    wallet = ZEDWalletCLI()
    wallet.cmdloop()
