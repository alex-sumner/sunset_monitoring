# Cryptocurrency Withdrawal Monitoring and Reporting System Specification

## 1. Introduction

This document outlines the specifications for a system designed to monitor a specific exchange smart contract deployed on multiple EVM chains. The system will detect failed `withdraw` function calls, send Telegram notifications when failures occur, and generate daily reports on withdrawal volumes and contract holdings. The primary goal is to ensure the exchange's hot wallet balances are not running low due to failed withdrawals and to provide comprehensive insights into daily on-chain activity, including the balances of key stablecoins held by the exchange contract.

## 2. Objectives

* **Timely Failed `withdraw` Detection:** Automatically identify failed calls to the `withdraw` function on the designated exchange contract across supported EVM blockchains via Alchemy, with notifications sent within 30 minutes of the failure occurring.
* **Notification for Failures:** Send alerts via Telegram for any detected failed `withdraw` transactions.
* **Balance Monitoring:** Provide visibility into the current balances of specific stablecoins (USDT, USDC, USDB) held by the designated exchange contract on each chain to preempt low balance issues, sourced from Alchemy.
* **Daily Reporting:** Generate a summary report of daily successful and failed `withdraw` calls, along with the current holdings of the monitored contract, including specified stablecoin balances, using data from Alchemy.
* **Security & Reliability:** Implement robust and secure methods for interacting with Alchemy's API and the Telegram Bot API.

## 3. Scope

This script will focus on monitoring outgoing transactions initiated from (or interacting with) the specified exchange smart contract addresses. It will specifically analyze calls to the `withdraw` function within these contracts. It will also monitor the balances of specified ERC-20 tokens held by these exchange contracts. It will interact exclusively with the Alchemy API (primarily using a polling mechanism) and the Telegram Bot API.

## 4. Supported Blockchains

All supported chains will be EVM-compatible and accessible via Alchemy. These include:

* Ethereum Mainnet
* Arbitrum One
* Base
* Sonic
* Blast

## 5. Technical Requirements

### 5.1. Blockchain Interaction (via Alchemy - Polling Approach)

* **Alchemy SDK/API:** Utilize Alchemy's comprehensive SDK (e.g., Python SDK) or direct API endpoints for periodic polling.
* **Contract ABI:** The Application Binary Interface (ABI) for the exchange contract, specifically including the `withdraw` function signature, is required to:
    * Decode input data of transactions to identify `withdraw` calls.
    * Potentially interpret more granular error reasons if the contract provides them in revert messages.
* **`withdraw` Function Signature:**
    ```solidity
    function withdraw(
        uint256 id,
        address trader,
        uint256 amount,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external
    ```
* **Monitoring Strategy (`withdraw` function calls):**
    1.  **Identify Potential `withdraw` Transactions:** Poll Alchemy's API (e.g., `eth_getLogs` for specific contract events if `withdraw` emits an event, or iterating through recent blocks via `eth_getBlockByNumber` and then `eth_getTransactionByHash` for transactions where the `to` address is the exchange contract address) for transactions targeting the exchange contract. Alchemy's `alchemy_getAssetTransfers` could also be useful here if the contract's `withdraw` function leads to transfers that Alchemy categorizes.
    2.  **Filter for `withdraw` Calls:** For each relevant transaction, inspect its `input` data. Use the contract ABI to decode the function selector and arguments to confirm it's a call to the `withdraw` function.
    3.  **Check Transaction Status:** Once a `withdraw` call is identified, retrieve its transaction receipt (using `eth_getTransactionReceipt`). A `status` of `0x0` indicates a failed transaction (reverted).
* **Balance Monitoring Strategy (ERC-20 Tokens):**
    * Utilize Alchemy's `alchemy_getTokenBalances` method to query the balance of specific ERC-20 tokens for the exchange contract address on its respective chain.
    * **Monitored Token Balances and Addresses:**
        * **Ethereum Mainnet:** USDT (Contract Address: `0xdAC17F958D2ee523a2206206994597C13D831ec7`)
        * **Arbitrum One:** USDC (Contract Address: `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`)
        * **Base:** USDC (Contract Address: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
        * **Sonic:** USDC (Contract Address: `0x29219dd400f2Bf60E5a23d13Be72B486D4038894`)
        * **Blast:** USDB (Contract Address: `0x4300000000000000000000000000000000000003`)
* **Transaction Status Interpretation:** A transaction receipt `status` of `0x0` explicitly indicates a failed transaction (revert). The system will specifically flag these for `withdraw` calls.

### 5.2. Telegram Notification System

* **Telegram Bot API:** Use the Telegram Bot API to send messages.
* **Bot Token:** Securely store and use a Telegram Bot Token.
* **Chat ID:** Configure the Telegram chat ID(s) where notifications will be sent (e.g., a dedicated group for operations).
* **Notification Content:**
    * **Failed Withdrawal Alert:**
        * Transaction Hash
        * Contract Address
        * Function Name: `withdraw`
        * Decoded Input Parameters (id, trader, amount) from the transaction's input data (if available and relevant for the alert).
        * Reason for failure (extracted from `revert` message if possible, using Alchemy's debug APIs or by trying to simulate the call to get a clearer error, though this might add complexity/cost).
        * Link to transaction on a relevant block explorer (e.g., Etherscan, Arbiscan, Basescan etc., constructed using the chain ID and transaction hash).
        * Chain name (e.g., Ethereum Mainnet, Arbitrum One)
    * **Low Balance Alert:**
        * Contract Address (the exchange contract)
        * Token Symbol (e.g., USDT, USDC, USDB)
        * Current Balance
        * Pre-defined Low Balance Threshold
        * Link to address on a relevant block explorer.
        * Chain name

### 5.3. Reporting Module

* **Data Collection (via Alchemy):**
    * **Daily Withdrawals (specific to `withdraw` function):** Collect all identified `withdraw` function calls (both successful and failed) from the exchange contract within a 24-hour period for each monitored chain, using Alchemy's historical transaction fetching.
    * **Holdings:** Capture the current balance of the monitored exchange contract for each chain at a specific time daily (e.g., midnight UTC), explicitly including the specified stablecoin balances (USDT, USDC, USDB) and native chain token balances.
* **Report Generation:**
    * Format: Plain text, Markdown, or CSV for easy readability and integration.
    * Content:
        * Date of report
        * For each chain and the specific exchange contract:
            * Total successful `withdraw` calls (count and total amount, if `amount` can be reliably extracted from input).
            * Total failed `withdraw` calls (count and total amount, if extractable).
            * List of failed `withdraw` transactions (details as per notification).
            * Current holdings of the contract (address, native token amount, and the specific ERC-20 token amounts: USDT on Ethereum, USDC on Arbitrum/Base/Sonic, USDB on Blast).
* **Delivery:** Send the daily report via Telegram to the configured chat(s).

### 5.4. System Architecture (High-Level)

* **Python Script:** The core logic will be implemented in Python.
* **Scheduler:** A cron job or similar scheduler will trigger the script at regular intervals (e.g., every 5-10 minutes for monitoring, daily for reporting).
* **Configuration File:** External configuration file (e.g., JSON, YAML) for Alchemy API keys, *exchange contract addresses per chain*, token contract addresses per chain, contract ABI, Telegram chat IDs, thresholds, polling intervals, etc.

## 6. Functional Requirements

### 6.1. Failed `withdraw` Detection

* Poll Alchemy's API at configurable intervals (e.g., every 5-10 minutes) to retrieve recent transactions where the `to` address is the exchange contract address across all supported EVM chains.
* For each such transaction, inspect its `input` data to confirm it's a call to the `withdraw` function using its signature from the ABI.
* Once a `withdraw` call is confirmed, retrieve its transaction receipt and check the `status` field.
* If the transaction `status` is `0x0` (failed), trigger a Telegram notification.
* Implement a mechanism to avoid duplicate notifications for the same failed transaction. This could involve storing processed transaction hashes (per chain) and their status.

### 6.2. Low Balance Alerting (Proactive)

* Periodically check the balances of the designated exchange contract on all supported EVM chains using Alchemy. This check will include the native token balance and the specified ERC-20 token balances for each chain. The frequency for balance checks can be less frequent than transaction monitoring (e.g., every hour).
* Define a configurable "low balance" threshold for each *specific token* (USDT, USDC, USDB, and native tokens like ETH) on each chain for the contract.
* If a balance falls below its threshold, send a Telegram alert.
* Implement rate-limiting for low balance alerts to prevent spam (e.g., only send once per hour if still below threshold).

### 6.3. Daily Reporting

* At a scheduled time (e.g., 00:00 UTC), compile:
    * A list of all `withdraw` function calls (successful and failed) from the past 24 hours on the monitored exchange contract across all supported chains, retrieved via Alchemy.
    * The current balances of the monitored exchange contract for all chains, explicitly including the USDT, USDC, and USDB balances as specified, retrieved via Alchemy.
* Generate a summary report and send it to Telegram.

## 7. Non-Functional Requirements

* **Performance:** The polling interval should be configured to meet the 30-minute notification window for failures while optimizing for Alchemy Compute Unit consumption. Alchemy's efficiency in fetching transaction data and receipts will be crucial.
* **Scalability:** Design should allow for easy addition of new EVM blockchain networks (as supported by Alchemy) and monitoring of additional contracts or functions if needed in the future.
* **Security:**
    * Alchemy API keys and sensitive information must be stored securely (e.g., environment variables, secret management systems, not directly in code).
    * Minimize permissions required for API keys.
* **Maintainability:** Clean, well-commented code, with clear separation of concerns (e.g., blockchain interaction, Telegram notification, reporting).
* **Error Handling:** Graceful handling of Alchemy API errors, rate limits, network issues, and unexpected data formats. Implement retries with exponential backoff for transient errors.
* **Logging:** Comprehensive logging of all activities, errors, and notifications, including when transactions are identified as `withdraw` calls and their final status, and balance checks.

## 8. Development Steps (High-Level)

1.  **Project Setup:**
    * Initialize Python project.
    * Install necessary libraries (e.g., `web3.py` configured for Alchemy providers, `python-telegram-bot` for Telegram interaction).
    * Set up configuration file structure for Alchemy API keys, *exchange contract addresses per chain*, *specific token contract addresses per chain*, contract ABI, Telegram chat IDs, low balance thresholds, polling intervals, etc.
2.  **Telegram Bot Integration:**
    * Create a Telegram bot via BotFather.
    * Implement functions to send messages to a specified chat ID.
3.  **Alchemy API and Web3.py Integration:**
    * Obtain Alchemy API keys.
    * Initialize `web3.py` instances for each supported chain, configured to use Alchemy as the provider.
    * Load the contract ABI for the exchange contract.
    * Develop functions to:
        * Get recent blocks/transactions for a given chain targeting the exchange contract.
        * Parse transaction `input` data to identify `withdraw` function calls using the ABI.
        * Retrieve transaction receipts by hash.
        * Get token balances for the contract address using `alchemy_getTokenBalances` for the specified ERC-20 tokens, and `eth_getBalance` for native currency.
4.  **Transaction Monitoring Logic (Polling):**
    * Implement a main loop that runs at the configured polling interval (e.g., every 5-10 minutes).
    * Within each loop:
        * For each configured chain and its exchange contract:
            * Fetch new blocks or transactions within a recent block range where the `to` address is the exchange contract address.
            * Iterate through these transactions.
            * If a transaction's `to` address matches the contract address and its `input` data's function selector matches the `withdraw` function:
                * Retrieve the transaction receipt.
                * Check the `status` field of the receipt.
                * If `status` is `0x0`, trigger a Telegram alert for a failed `withdraw` transaction, including decoded parameters like `id`, `trader`, and `amount`.
                * Record the transaction hash, its status, and relevant decoded data for reporting, ensuring no duplicate notifications.
5.  **Balance Monitoring Logic (Polling):**
    * Implement a separate function to periodically check balances (native token and the specified ERC-20 tokens) of the contract on each chain using Alchemy. This can run on a less frequent schedule (e.g., every hour).
    * For each specified token on its respective chain, query the exchange contract's balance.
    * Compare the retrieved balance against configured low balance thresholds and send Telegram alerts if breached.
6.  **Reporting Logic:**
    * Develop functions to aggregate daily `withdraw` transaction data (success/fail) and current contract holdings (including the specified stablecoin balances) across all chains.
    * Format the daily report, clearly separating data by chain and providing specific details on `withdraw` calls and all monitored balances.
7.  **Scheduling:**
    * Set up a cron job or equivalent to trigger the main monitoring script at the desired polling interval.
    * Set up a separate cron job for daily report generation.
8.  **Error Handling and Logging:**
    * Implement robust `try-except` blocks around all API calls and data processing.
    * Integrate a logging library (e.g., Python's `logging` module) to record all activities, warnings, and errors.
9.  **Testing:**
    * Unit tests for individual functions (e.g., ABI decoding, status checking, balance fetching).
    * Integration tests for the entire system (using Alchemy's testnet endpoints for each supported chain and mock Telegram interactions). Simulate successful and failed `withdraw` transactions on testnets to verify detection and notification. Verify correct balance retrieval and low balance alerts.
