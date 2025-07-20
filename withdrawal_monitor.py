import logging
import json
import time
from typing import Dict, List, Set
from datetime import datetime, timezone, timedelta
from blockchain_monitor import BlockchainMonitor, Transaction
from telegram_notifier import TelegramNotifier


class WithdrawalMonitor:
    def __init__(self, config: Dict):
        self.config = config
        self.blockchain_monitor = BlockchainMonitor(config)
        self.telegram_notifier = TelegramNotifier(config)
        self.logger = logging.getLogger(__name__)
        
        # Track processed transactions to avoid duplicates
        self.processed_transactions: Set[str] = set()
        
        # Storage for daily reporting
        self.daily_transactions: Dict[str, List[Transaction]] = {}
        
        # Load processed transactions from file if exists
        self._load_processed_transactions()
        
        # Load daily transactions from file if exists
        self._load_daily_transactions()
    
    def _load_processed_transactions(self):
        """Load processed transactions from file to avoid duplicates on restart"""
        try:
            with open('processed_transactions.json', 'r') as f:
                data = json.load(f)
                self.processed_transactions = set(data.get('processed_transactions', []))
                self.logger.info(f"Loaded {len(self.processed_transactions)} processed transactions")
        except FileNotFoundError:
            self.logger.info("No processed transactions file found, starting fresh")
        except Exception as e:
            self.logger.error(f"Error loading processed transactions: {str(e)}")
    
    def _save_processed_transactions(self):
        """Save processed transactions to file"""
        try:
            # Keep only recent transactions to prevent file from growing too large
            # Remove transactions older than 7 days
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
            
            data = {
                'processed_transactions': list(self.processed_transactions),
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            
            with open('processed_transactions.json', 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving processed transactions: {str(e)}")
    
    def _load_daily_transactions(self):
        """Load daily transactions from file for reporting persistence"""
        try:
            with open('daily_transactions.json', 'r') as f:
                data = json.load(f)
                
                # Rebuild daily_transactions with Transaction objects
                for chain_name, tx_list in data.get('daily_transactions', {}).items():
                    self.daily_transactions[chain_name] = []
                    
                    for tx_data in tx_list:
                        # Recreate Transaction object
                        from blockchain_monitor import Transaction
                        tx = Transaction(
                            hash=tx_data['hash'],
                            block_number=tx_data['block_number'],
                            status=tx_data['status'],
                            chain=tx_data['chain'],
                            contract_address=tx_data['contract_address'],
                            function_name=tx_data['function_name'],
                            decoded_params=tx_data['decoded_params'],
                            timestamp=datetime.fromisoformat(tx_data['timestamp']),
                            gas_used=tx_data['gas_used'],
                            explorer_url=tx_data['explorer_url']
                        )
                        self.daily_transactions[chain_name].append(tx)
                
                total_loaded = sum(len(txs) for txs in self.daily_transactions.values())
                self.logger.info(f"Loaded {total_loaded} daily transactions from file")
                
        except FileNotFoundError:
            self.logger.info("No daily transactions file found, starting fresh")
        except Exception as e:
            self.logger.error(f"Error loading daily transactions: {str(e)}")
    
    def _save_daily_transactions(self):
        """Save daily transactions to file for persistence"""
        try:
            # Convert Transaction objects to serializable format
            data = {
                'daily_transactions': {},
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            
            for chain_name, tx_list in self.daily_transactions.items():
                data['daily_transactions'][chain_name] = []
                
                for tx in tx_list:
                    tx_data = {
                        'hash': tx.hash,
                        'block_number': tx.block_number,
                        'status': tx.status,
                        'chain': tx.chain,
                        'contract_address': tx.contract_address,
                        'function_name': tx.function_name,
                        'decoded_params': tx.decoded_params,
                        'timestamp': tx.timestamp.isoformat(),
                        'gas_used': tx.gas_used,
                        'explorer_url': tx.explorer_url
                    }
                    data['daily_transactions'][chain_name].append(tx_data)
            
            with open('daily_transactions.json', 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving daily transactions: {str(e)}")
    
    def monitor_withdrawals(self) -> List[Transaction]:
        """Monitor for new withdrawal transactions across all chains"""
        all_transactions = []
        
        for chain_name in self.config['chains'].keys():
            try:
                self.logger.info(f"Checking for new transactions on {chain_name}")
                
                # Get recent transactions
                recent_transactions = self.blockchain_monitor.get_recent_transactions(chain_name)
                
                for tx_data in recent_transactions:
                    tx_hash = tx_data['hash']
                    
                    # Skip if already processed
                    if tx_hash in self.processed_transactions:
                        continue
                    
                    # Get transaction receipt
                    receipt = self.blockchain_monitor.get_transaction_receipt(chain_name, tx_hash)
                    
                    if receipt is None:
                        self.logger.warning(f"Could not get receipt for transaction {tx_hash}")
                        continue
                    
                    # Create transaction object
                    transaction = self.blockchain_monitor.create_transaction_object(
                        chain_name, tx_data, receipt
                    )
                    
                    all_transactions.append(transaction)
                    
                    # Add to processed set
                    self.processed_transactions.add(tx_hash)
                    
                    # Store for daily reporting
                    if chain_name not in self.daily_transactions:
                        self.daily_transactions[chain_name] = []
                    self.daily_transactions[chain_name].append(transaction)
                    
                    # Send alert if transaction failed
                    if not transaction.status:
                        self.logger.warning(f"Failed withdrawal detected: {tx_hash} on {chain_name}")
                        
                        try:
                            self.telegram_notifier.send_failed_withdrawal_alert(transaction)
                        except Exception as e:
                            self.logger.error(f"Error sending failed withdrawal alert: {str(e)}")
                    else:
                        self.logger.info(f"Successful withdrawal: {tx_hash} on {chain_name}")
                
            except Exception as e:
                self.logger.error(f"Error monitoring withdrawals on {chain_name}: {str(e)}")
                continue
        
        # Save processed transactions and daily transactions
        self._save_processed_transactions()
        self._save_daily_transactions()
        
        return all_transactions
    
    def get_daily_statistics(self, date: datetime = None) -> Dict:
        """Get daily statistics for all chains"""
        if date is None:
            date = datetime.now(timezone.utc)
        
        stats = {}
        
        for chain_name in self.config['chains'].keys():
            chain_transactions = self.daily_transactions.get(chain_name, [])
            
            # Filter transactions for the specific date
            daily_transactions = [
                tx for tx in chain_transactions 
                if tx.timestamp.date() == date.date()
            ]
            
            successful_transactions = [tx for tx in daily_transactions if tx.status]
            failed_transactions = [tx for tx in daily_transactions if not tx.status]
            
            stats[chain_name] = {
                'successful_withdrawals': len(successful_transactions),
                'failed_withdrawals': len(failed_transactions),
                'total_withdrawals': len(daily_transactions),
                'successful_transactions': [
                    {
                        'hash': tx.hash,
                        'block_number': tx.block_number,
                        'timestamp': tx.timestamp.isoformat(),
                        'decoded_params': tx.decoded_params
                    }
                    for tx in successful_transactions
                ],
                'failed_transactions': [
                    {
                        'hash': tx.hash,
                        'block_number': tx.block_number,
                        'timestamp': tx.timestamp.isoformat(),
                        'decoded_params': tx.decoded_params,
                        'explorer_url': tx.explorer_url
                    }
                    for tx in failed_transactions
                ]
            }
        
        return stats
    
    def get_daily_statistics_for_period(self, start_time: datetime, end_time: datetime) -> Dict:
        """Get statistics for a specific time period (24-hour window)"""
        stats = {}
        
        for chain_name in self.config['chains'].keys():
            chain_transactions = self.daily_transactions.get(chain_name, [])
            
            # Filter transactions for the specific time period
            period_transactions = [
                tx for tx in chain_transactions 
                if start_time <= tx.timestamp <= end_time
            ]
            
            successful_transactions = [tx for tx in period_transactions if tx.status]
            failed_transactions = [tx for tx in period_transactions if not tx.status]
            
            stats[chain_name] = {
                'successful_withdrawals': len(successful_transactions),
                'failed_withdrawals': len(failed_transactions),
                'total_withdrawals': len(period_transactions),
                'successful_transactions': [
                    {
                        'hash': tx.hash,
                        'block_number': tx.block_number,
                        'timestamp': tx.timestamp.isoformat(),
                        'decoded_params': tx.decoded_params
                    }
                    for tx in successful_transactions
                ],
                'failed_transactions': [
                    {
                        'hash': tx.hash,
                        'block_number': tx.block_number,
                        'timestamp': tx.timestamp.isoformat(),
                        'decoded_params': tx.decoded_params,
                        'explorer_url': tx.explorer_url
                    }
                    for tx in failed_transactions
                ]
            }
        
        return stats
    
    def cleanup_old_data(self, days_to_keep: int = 7):
        """Clean up old transaction data to prevent memory issues"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        
        for chain_name in list(self.daily_transactions.keys()):
            # Filter out old transactions
            self.daily_transactions[chain_name] = [
                tx for tx in self.daily_transactions[chain_name]
                if tx.timestamp > cutoff_time
            ]
            
            # Remove empty chains
            if not self.daily_transactions[chain_name]:
                del self.daily_transactions[chain_name]
        
        # Clean up processed transactions set
        # Note: This is a simplified cleanup - in a production system,
        # you might want to store transaction timestamps to do this properly
        if len(self.processed_transactions) > 10000:  # Arbitrary limit
            # Keep only the most recent 5000 transactions
            self.processed_transactions = set(list(self.processed_transactions)[-5000:])
            self._save_processed_transactions()
        
        self.logger.info(f"Cleaned up data older than {days_to_keep} days")
    
    def run_single_check(self):
        """Run a single monitoring check"""
        try:
            self.logger.info("Starting withdrawal monitoring check...")
            
            # Monitor withdrawals
            transactions = self.monitor_withdrawals()
            
            if transactions:
                self.logger.info(f"Processed {len(transactions)} withdrawal transactions")
                
                # Log summary
                successful_count = sum(1 for tx in transactions if tx.status)
                failed_count = sum(1 for tx in transactions if not tx.status)
                
                self.logger.info(f"Successful: {successful_count}, Failed: {failed_count}")
                
                if failed_count > 0:
                    self.logger.warning(f"⚠️ {failed_count} failed withdrawals detected!")
            else:
                self.logger.info("No new withdrawal transactions found")
            
            # Cleanup old data periodically
            if len(self.daily_transactions) > 0:
                self.cleanup_old_data()
                
        except Exception as e:
            self.logger.error(f"Error in withdrawal monitoring check: {str(e)}")
            
            # Send error notification
            try:
                self.telegram_notifier.send_error_notification(
                    f"Withdrawal monitoring error: {str(e)}", 
                    "WithdrawalMonitor"
                )
            except Exception as notify_error:
                self.logger.error(f"Failed to send error notification: {str(notify_error)}")
    
    def get_system_status(self) -> Dict:
        """Get current system status"""
        status = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'processed_transactions_count': len(self.processed_transactions),
            'daily_transactions_count': sum(
                len(txs) for txs in self.daily_transactions.values()
            ),
            'chains_monitored': list(self.config['chains'].keys()),
            'last_processed_blocks': self.blockchain_monitor.last_processed_blocks.copy()
        }
        
        return status