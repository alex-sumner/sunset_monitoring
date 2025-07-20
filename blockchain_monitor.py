import json
import logging
import time
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from web3.exceptions import TransactionNotFound, BlockNotFound
import requests
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Transaction:
    hash: str
    block_number: int
    status: bool
    chain: str
    contract_address: str
    function_name: str
    decoded_params: Dict
    timestamp: datetime
    gas_used: int
    explorer_url: str


@dataclass
class BalanceInfo:
    chain: str
    contract_address: str
    token_symbol: str
    token_address: str
    balance: float
    threshold: float
    is_below_threshold: bool
    explorer_url: str


class BlockchainMonitor:
    def __init__(self, config: Dict):
        self.config = config
        self.web3_instances = {}
        self.contract_abis = {}
        self.logger = logging.getLogger(__name__)
        
        # Initialize Web3 instances for each chain
        self._setup_web3_instances()
        
        # Load contract ABI
        self._load_contract_abi()
        
        # Storage for last processed blocks
        self.last_processed_blocks = {}
        
    def _setup_web3_instances(self):
        """Initialize Web3 instances for each supported chain"""
        for chain_name, chain_config in self.config['chains'].items():
            api_key = self.config['alchemy']['api_keys'][chain_name]
            rpc_url = chain_config['rpc_url'] + api_key
            
            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url))
                if w3.is_connected():
                    self.web3_instances[chain_name] = w3
                    self.logger.info(f"Connected to {chain_name} via Alchemy")
                else:
                    self.logger.error(f"Failed to connect to {chain_name}")
            except Exception as e:
                self.logger.error(f"Error connecting to {chain_name}: {str(e)}")
    
    def _load_contract_abi(self):
        """Load the contract ABI for withdraw function"""
        # Minimal ABI for withdraw function
        withdraw_abi = [
            {
                "inputs": [
                    {"name": "id", "type": "uint256"},
                    {"name": "trader", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "v", "type": "uint8"},
                    {"name": "r", "type": "bytes32"},
                    {"name": "s", "type": "bytes32"}
                ],
                "name": "withdraw",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
        
        # ERC20 ABI for balance checking
        erc20_abi = [
            {
                "inputs": [{"name": "owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        self.contract_abis = {
            'withdraw': withdraw_abi,
            'erc20': erc20_abi
        }
    
    def get_recent_transactions(self, chain_name: str, start_block: Optional[int] = None) -> List[Dict]:
        """Get recent transactions to the exchange contract using event logs (more efficient)"""
        if chain_name not in self.web3_instances:
            self.logger.error(f"No Web3 instance for chain: {chain_name}")
            return []
        
        w3 = self.web3_instances[chain_name]
        contract_address = self.config['exchange_contracts'][chain_name]
        
        try:
            current_block = w3.eth.block_number
            
            # Determine start block
            if start_block is None:
                if chain_name in self.last_processed_blocks:
                    start_block = self.last_processed_blocks[chain_name] + 1
                else:
                    start_block = current_block - self.config['monitoring']['initial_block_range']
            
            # Log block range being scanned
            if start_block <= current_block:
                self.logger.info(f"Scanning blocks {start_block} to {current_block} on {chain_name} ({current_block - start_block + 1} blocks)")
            else:
                self.logger.info(f"No new blocks to scan on {chain_name} (current: {current_block}, last processed: {self.last_processed_blocks.get(chain_name, 'none')})")
            
            # Update last processed block
            self.last_processed_blocks[chain_name] = current_block
            
            transactions = []
            
            # Use event logs to find transactions to our contract (much more efficient)
            try:
                # Get all transactions to our contract address
                checksum_address = Web3.to_checksum_address(contract_address)
                
                # Chunk the block range to avoid 500-block limits
                max_blocks_per_request = 500
                all_logs = []
                
                for chunk_start in range(start_block, current_block + 1, max_blocks_per_request):
                    chunk_end = min(chunk_start + max_blocks_per_request - 1, current_block)
                    
                    self.logger.debug(f"Getting logs for {chain_name}: fromBlock={chunk_start}, toBlock={chunk_end}, address={checksum_address}")
                    
                    chunk_logs = w3.eth.get_logs({
                        'fromBlock': chunk_start,
                        'toBlock': chunk_end,
                        'address': checksum_address
                    })
                    
                    all_logs.extend(chunk_logs)
                
                # Get unique transaction hashes
                tx_hashes = list(set(log.transactionHash.hex() for log in all_logs))
                
                self.logger.info(f"Found {len(tx_hashes)} transactions to contract on {chain_name}")
                
                # Check each transaction
                for tx_hash in tx_hashes:
                    try:
                        tx = w3.eth.get_transaction(tx_hash)
                        
                        # Check if it's a withdraw function call
                        if self._is_withdraw_function(tx.input):
                            # Get block timestamp
                            block = w3.eth.get_block(tx.blockNumber)
                            
                            transactions.append({
                                'hash': tx_hash,
                                'block_number': tx.blockNumber,
                                'input': tx.input.hex(),
                                'to': tx.to,
                                'from': tx['from'],
                                'value': tx.value,
                                'gas': tx.gas,
                                'gasPrice': tx.gasPrice,
                                'timestamp': datetime.fromtimestamp(block.timestamp, timezone.utc)
                            })
                    
                    except Exception as e:
                        self.logger.error(f"Error processing transaction {tx_hash} on {chain_name}: {str(e)}")
                        continue
                
            except Exception as e:
                self.logger.error(f"Event log approach failed on {chain_name}: {str(e)}")
                # No fallback - just return empty transactions list
            
            self.logger.info(f"Found {len(transactions)} withdraw transactions on {chain_name}")
            return transactions
            
        except Exception as e:
            self.logger.error(f"Error getting recent transactions for {chain_name}: {str(e)}")
            return []
    
    def _is_withdraw_function(self, input_data: bytes) -> bool:
        """Check if transaction input data is a withdraw function call"""
        if len(input_data) < 4:
            return False
        
        # Get function selector (first 4 bytes)
        function_selector = input_data[:4]
        
        # Calculate withdraw function selector
        w3 = Web3()
        withdraw_selector = w3.keccak(text="withdraw(uint256,address,uint256,uint8,bytes32,bytes32)")[:4]
        
        return function_selector == withdraw_selector
    
    def get_transaction_receipt(self, chain_name: str, tx_hash: str) -> Optional[Dict]:
        """Get transaction receipt and check if it failed"""
        if chain_name not in self.web3_instances:
            return None
        
        w3 = self.web3_instances[chain_name]
        
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            return {
                'hash': tx_hash,
                'status': receipt.status,
                'block_number': receipt.blockNumber,
                'gas_used': receipt.gasUsed,
                'failed': receipt.status == 0
            }
        except TransactionNotFound:
            self.logger.warning(f"Transaction {tx_hash} not found on {chain_name}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting receipt for {tx_hash} on {chain_name}: {str(e)}")
            return None
    
    def decode_withdraw_params(self, input_data: str) -> Dict:
        """Decode withdraw function parameters from transaction input"""
        try:
            w3 = Web3()
            
            # Remove 0x prefix if present
            if input_data.startswith('0x'):
                input_data = input_data[2:]
            
            # Convert to bytes
            input_bytes = bytes.fromhex(input_data)
            
            # Skip function selector (first 4 bytes)
            params_data = input_bytes[4:]
            
            # Decode parameters
            # withdraw(uint256 id, address trader, uint256 amount, uint8 v, bytes32 r, bytes32 s)
            decoded = w3.codec.decode(['uint256', 'address', 'uint256', 'uint8', 'bytes32', 'bytes32'], params_data)
            
            return {
                'id': decoded[0],
                'trader': decoded[1],
                'amount': decoded[2],
                'v': decoded[3],
                'r': decoded[4].hex(),
                's': decoded[5].hex()
            }
        except Exception as e:
            self.logger.error(f"Error decoding withdraw parameters: {str(e)}")
            return {}
    
    def get_token_balance(self, chain_name: str, token_address: str, holder_address: str) -> Optional[float]:
        """Get ERC20 token balance"""
        if chain_name not in self.web3_instances:
            return None
        
        w3 = self.web3_instances[chain_name]
        
        try:
            # Create contract instance
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.contract_abis['erc20']
            )
            
            # Get balance
            balance = contract.functions.balanceOf(Web3.to_checksum_address(holder_address)).call()
            
            # Get decimals
            decimals = contract.functions.decimals().call()
            
            # Convert to human readable format
            human_balance = balance / (10 ** decimals)
            
            return human_balance
            
        except Exception as e:
            self.logger.error(f"Error getting token balance for {token_address} on {chain_name}: {str(e)}")
            return None
    
    def get_native_balance(self, chain_name: str, address: str) -> Optional[float]:
        """Get native token balance (ETH, etc.)"""
        if chain_name not in self.web3_instances:
            return None
        
        w3 = self.web3_instances[chain_name]
        
        try:
            balance_wei = w3.eth.get_balance(Web3.to_checksum_address(address))
            balance_eth = w3.from_wei(balance_wei, 'ether')
            return float(balance_eth)
        except Exception as e:
            self.logger.error(f"Error getting native balance for {address} on {chain_name}: {str(e)}")
            return None
    
    def check_all_balances(self) -> List[BalanceInfo]:
        """Check all configured token balances"""
        balance_info = []
        
        for chain_name, chain_tokens in self.config['tokens'].items():
            contract_address = self.config['exchange_contracts'][chain_name]
            explorer_url = self.config['chains'][chain_name]['explorer_url']
            
            # Check native token balance
            if 'native' in chain_tokens:
                native_balance = self.get_native_balance(chain_name, contract_address)
                if native_balance is not None:
                    threshold = chain_tokens['native']['threshold']
                    balance_info.append(BalanceInfo(
                        chain=chain_name,
                        contract_address=contract_address,
                        token_symbol='ETH' if chain_name != 'sonic' else 'S',
                        token_address='native',
                        balance=native_balance,
                        threshold=threshold,
                        is_below_threshold=native_balance < threshold,
                        explorer_url=f"{explorer_url}/address/{contract_address}"
                    ))
            
            # Check ERC20 token balances
            for token_symbol, token_config in chain_tokens.items():
                if token_symbol == 'native':
                    continue
                
                token_address = token_config['address']
                threshold = token_config['threshold']
                
                token_balance = self.get_token_balance(chain_name, token_address, contract_address)
                if token_balance is not None:
                    balance_info.append(BalanceInfo(
                        chain=chain_name,
                        contract_address=contract_address,
                        token_symbol=token_symbol.upper(),
                        token_address=token_address,
                        balance=token_balance,
                        threshold=threshold,
                        is_below_threshold=token_balance < threshold,
                        explorer_url=f"{explorer_url}/address/{contract_address}"
                    ))
        
        return balance_info
    
    def create_transaction_object(self, chain_name: str, tx_data: Dict, receipt: Dict) -> Transaction:
        """Create a Transaction object from transaction data and receipt"""
        explorer_url = self.config['chains'][chain_name]['explorer_url']
        decoded_params = self.decode_withdraw_params(tx_data['input'])
        
        return Transaction(
            hash=tx_data['hash'],
            block_number=tx_data['block_number'],
            status=receipt['status'] == 1,
            chain=chain_name,
            contract_address=tx_data['to'],
            function_name='withdraw',
            decoded_params=decoded_params,
            timestamp=tx_data['timestamp'],
            gas_used=receipt['gas_used'],
            explorer_url=f"{explorer_url}/tx/{tx_data['hash']}"
        )