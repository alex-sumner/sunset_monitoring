import logging
from typing import Dict, List
from datetime import datetime, timezone
from blockchain_monitor import BlockchainMonitor, BalanceInfo
from telegram_notifier import TelegramNotifier


class BalanceMonitor:
    def __init__(self, config: Dict):
        self.config = config
        self.blockchain_monitor = BlockchainMonitor(config)
        self.telegram_notifier = TelegramNotifier(config)
        self.logger = logging.getLogger(__name__)
        
        # Track balance history for reporting
        self.balance_history: List[Dict] = []
    
    def check_all_balances(self) -> List[BalanceInfo]:
        """Check all configured token balances across all chains"""
        try:
            self.logger.info("Checking all token balances...")
            
            balance_info = self.blockchain_monitor.check_all_balances()
            
            # Log balance status
            for balance in balance_info:
                chain_name = self.config['chains'][balance.chain]['name']
                
                if balance.is_below_threshold:
                    self.logger.warning(
                        f"LOW BALANCE: {balance.token_symbol} on {chain_name} - "
                        f"Balance: {balance.balance}, Threshold: {balance.threshold}"
                    )
                else:
                    self.logger.info(
                        f"OK: {balance.token_symbol} on {chain_name} - "
                        f"Balance: {balance.balance}"
                    )
            
            # Store balance snapshot for history
            self._store_balance_snapshot(balance_info)
            
            return balance_info
            
        except Exception as e:
            self.logger.error(f"Error checking balances: {str(e)}")
            return []
    
    def _store_balance_snapshot(self, balance_info: List[BalanceInfo]):
        """Store balance snapshot for historical tracking"""
        snapshot = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'balances': []
        }
        
        for balance in balance_info:
            snapshot['balances'].append({
                'chain': balance.chain,
                'token_symbol': balance.token_symbol,
                'token_address': balance.token_address,
                'balance': balance.balance,
                'threshold': balance.threshold,
                'is_below_threshold': balance.is_below_threshold,
                'contract_address': balance.contract_address
            })
        
        self.balance_history.append(snapshot)
        
        # Keep only the last 24 hours of snapshots (assuming hourly checks)
        if len(self.balance_history) > 24:
            self.balance_history = self.balance_history[-24:]
    
    def send_low_balance_alerts(self, balance_info: List[BalanceInfo]):
        """Send Telegram alerts for low balances"""
        low_balance_count = 0
        
        for balance in balance_info:
            if balance.is_below_threshold:
                try:
                    success = self.telegram_notifier.send_low_balance_alert(balance)
                    if success:
                        low_balance_count += 1
                        self.logger.info(f"Sent low balance alert for {balance.token_symbol} on {balance.chain}")
                    else:
                        self.logger.error(f"Failed to send low balance alert for {balance.token_symbol} on {balance.chain}")
                except Exception as e:
                    self.logger.error(f"Error sending low balance alert: {str(e)}")
        
        if low_balance_count > 0:
            self.logger.warning(f"Sent {low_balance_count} low balance alerts")
    
    def get_balance_summary(self) -> Dict:
        """Get current balance summary for all chains"""
        balance_info = self.check_all_balances()
        
        summary = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'chains': {}
        }
        
        for balance in balance_info:
            if balance.chain not in summary['chains']:
                summary['chains'][balance.chain] = {
                    'name': self.config['chains'][balance.chain]['name'],
                    'balances': []
                }
            
            summary['chains'][balance.chain]['balances'].append({
                'token_symbol': balance.token_symbol,
                'token_address': balance.token_address,
                'balance': balance.balance,
                'threshold': balance.threshold,
                'is_below_threshold': balance.is_below_threshold,
                'status': 'LOW' if balance.is_below_threshold else 'OK'
            })
        
        return summary
    
    def get_balance_trends(self, hours: int = 24) -> Dict:
        """Get balance trends over the specified number of hours"""
        if len(self.balance_history) < 2:
            return {'error': 'Insufficient data for trend analysis'}
        
        trends = {}
        
        # Get the latest and oldest snapshots within the time range
        latest_snapshot = self.balance_history[-1]
        oldest_snapshot = self.balance_history[max(0, len(self.balance_history) - hours)]
        
        # Calculate trends for each token
        latest_balances = {f"{b['chain']}_{b['token_symbol']}": b for b in latest_snapshot['balances']}
        oldest_balances = {f"{b['chain']}_{b['token_symbol']}": b for b in oldest_snapshot['balances']}
        
        for key, latest_balance in latest_balances.items():
            if key in oldest_balances:
                oldest_balance = oldest_balances[key]
                
                change = latest_balance['balance'] - oldest_balance['balance']
                change_percent = (change / oldest_balance['balance']) * 100 if oldest_balance['balance'] > 0 else 0
                
                trends[key] = {
                    'chain': latest_balance['chain'],
                    'token_symbol': latest_balance['token_symbol'],
                    'current_balance': latest_balance['balance'],
                    'previous_balance': oldest_balance['balance'],
                    'change': change,
                    'change_percent': change_percent,
                    'trend': 'increasing' if change > 0 else 'decreasing' if change < 0 else 'stable'
                }
        
        return {
            'period_hours': hours,
            'trends': trends,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def run_balance_check(self):
        """Run a complete balance check cycle"""
        try:
            self.logger.info("Starting balance monitoring check...")
            
            # Check all balances
            balance_info = self.check_all_balances()
            
            if not balance_info:
                self.logger.warning("No balance information retrieved")
                return
            
            # Send alerts for low balances
            self.send_low_balance_alerts(balance_info)
            
            # Log summary
            total_balances = len(balance_info)
            low_balances = sum(1 for b in balance_info if b.is_below_threshold)
            
            self.logger.info(f"Balance check completed: {total_balances} balances checked, {low_balances} below threshold")
            
            if low_balances > 0:
                self.logger.warning(f"⚠️ {low_balances} token balances are below threshold!")
            
        except Exception as e:
            self.logger.error(f"Error in balance monitoring check: {str(e)}")
            
            # Send error notification
            try:
                self.telegram_notifier.send_error_notification(
                    f"Balance monitoring error: {str(e)}", 
                    "BalanceMonitor"
                )
            except Exception as notify_error:
                self.logger.error(f"Failed to send error notification: {str(notify_error)}")
    
    def get_critical_balances(self, threshold_multiplier: float = 0.5) -> List[BalanceInfo]:
        """Get balances that are critically low (below threshold * multiplier)"""
        balance_info = self.check_all_balances()
        
        critical_balances = []
        for balance in balance_info:
            critical_threshold = balance.threshold * threshold_multiplier
            if balance.balance < critical_threshold:
                critical_balances.append(balance)
        
        return critical_balances
    
    def cleanup_old_history(self, hours_to_keep: int = 168):  # 7 days
        """Clean up old balance history to prevent memory issues"""
        if len(self.balance_history) > hours_to_keep:
            self.balance_history = self.balance_history[-hours_to_keep:]
            self.logger.info(f"Cleaned up balance history, keeping last {hours_to_keep} hours")
    
    def get_system_status(self) -> Dict:
        """Get balance monitoring system status"""
        status = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'balance_history_count': len(self.balance_history),
            'chains_monitored': list(self.config['chains'].keys()),
            'tokens_monitored': []
        }
        
        # Count tokens monitored per chain
        for chain_name, chain_tokens in self.config['tokens'].items():
            for token_symbol in chain_tokens.keys():
                status['tokens_monitored'].append(f"{chain_name}_{token_symbol}")
        
        return status