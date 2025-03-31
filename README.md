# **Zedovium Blockchain Documentation**  

## **📌 Overview**  
Zedovium is a **Proof-of-Work (PoW) blockchain** with dynamic transaction fees, miner difficulty adjustments, and a unique **Zedovium Guard** mechanism to prevent mining centralization . This document explains all network endpoints, economic rules, and security features in detail. This is still under heavy development!

---

## **🔗 Core Features**  

### **1. Dynamic Transaction Fees**  
- **Fee Range** 1% (min) to 5% (max) of transaction value 

- **Adjustment Mechanism**
  - Fee scales **linearly** with mempool congestion  
  - Formula:  
    ```  
    fee = min(base_fee + (mempool_fullness × (max_fee - base_fee)), max_fee)  
    ```  
  - Rounded to nearest **0.1%** increment for cleaner UX  

- **Mempool Impact**
  - Higher fees incentivize miners to prioritize transactions during congestion  
  - Lower fees when mempool is empty (1% floor)  

### **2. Hashing Algorithm (BLAKE2b)**  

- Used for
  - **Block hashing** (`calculate_hash` in `Block` class)  
  - **Transaction IDs** (`calculate_txid`) 

- Benefits
  - Faster than SHA-3 while maintaining security  
  - Resistant to ASIC mining (helps decentralization)  

### **3. Difficulty Adjustment**  
- **Target Block Time**: **5 minutes**  
- **Adjusts Every**: **12 blocks (~1 hour)**  
- **Formula**:  
  - If blocks are too fast → **Increase difficulty**  
  - If blocks are too slow → **Decrease difficulty**  

---

## **📡 Network & API Endpoints**  

### **🔹 Blockchain Info**  
| Endpoint | Description |  
|----------|-------------|  
| `GET /network/info` | Chain height, difficulty, supply |  
| `GET /network/chain` | Full blockchain data |  
| `GET /network/latestblock` | Latest block details |  
| `GET /network/hashrate` | Estimated network hashrate |  

### **🔹 Transactions & Fees**  
| Endpoint | Description |  
|----------|-------------|  
| `POST /transaction/create` | Submit a new transaction |  
| `GET /network/fee_estimate` | Current fee rate & mempool status |  
| `GET /network/fee_chart` | Fee structure visualization |  

### **🔹 Mining**  
| Endpoint | Description |  
|----------|-------------|  
| `GET /mining/info` | Current difficulty & latest block |  
| `POST /mining/submitblock` | Submit a mined block |  

### **🔹 Wallet & Addresses**  
| Endpoint | Description |  
|----------|-------------|  
| `GET /wallet/create` | Generate a new wallet (address + seed) |  
| `POST /wallet/import` | Import wallet using seed |  
| `GET /wallet/validate/<addr>` | Check if address is valid |  
| `GET /user/balance/<addr>` | Get balance for an address |  

### **🔹 Zedovium Guard**  
| Endpoint | Description |  
|----------|-------------|  
| `GET /network/checkaddrdiff/<addr>` | Check if miner is under high difficulty |  

---

## **⚙️ Technical Details**  

### **📌 Address Generation**  
- **Format**: `ZED-[4 words]-[checksum]` (e.g., `ZED-sunset-cat-moon-tree-1a3f`)  
- **Derived from**:  
  - BIP-39 wordlist (`words.txt`)  
  - SHA-256 hashing of seed  
- **Checksum**: First 4 chars of `SHA256(phrase)`  

### **📌 Mempool Mechanics**  
- **Max Size**: **10,000 transactions**  
- **Block Limit**: **512 transactions/block**  
- **Prioritization**: Sorts by **highest fee**  

---

## **🔒 Security Notes**  
- **Zedovium Guard** prevents 51% attacks by penalizing fast miners.  
- **Dynamic fees** reduce spam transactions.  
- **Seed phrases** must be kept secure (wallet recovery depends on them).  

## **🔐 Security & Anti-Centralization**  


### **Zedovium Guard Mechanism**  

- **Purpose**: Prevent mining monopolies. 

- **How It Works**:  

  1. Tracks **each miner’s block rate**.  
  2. If a miner exceeds **10 blocks/hour**, their **difficulty increases by 50% per extra block**.  
  3. Returns to normal if activity slows.  

- **Endpoint**:  
  - `GET /network/checkaddrdiff/<address>` → Check if a miner is penalized.  

📌 **Example**:  
- Miner A submits **15 blocks/hour** → **Difficulty × 2.5** (slowing them down).  

---

## **💰 Tokenomics (ZED Coin)**  

| **Parameter** | **Value** | **Description** |  
|--------------|----------|----------------|  
| **Block Reward** | 80 ZED | New coins per block |  
| **Transaction Fee** | 1%–5% | Dynamic, scales with demand |  
| **Max Supply** | Uncapped (for now) | Adjustable via governance |  

📌 **Key Insight**:  
- Miners earn **80 ZED** per block.  
- Fees **do not burn**—they go to a **Zedovium Developer Fund** (basically my wallet XD)

---

## **📜 License**  
GNU General Public License v3.0  

---

### **🎯 Summary**  
✅ **Dynamic fees** prevent congestion exploitation  
✅ **Zedovium Guard** keeps mining decentralized  
✅ **BLAKE2b** ensures fast & secure hashing  
✅ **Full Web3 RPC** support for compatibility  

For more details, check the [OpenAPI spec](#) (if implemented).
Check out the [Discord](https://discord.gg/zYdeBw7gwB)

🚀 **Happy mining!** 🚀