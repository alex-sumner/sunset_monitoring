import logging
from typing import Dict, List
from datetime import datetime, timezone, timedelta
from withdrawal_monitor import WithdrawalMonitor
from balance_monitor import BalanceMonitor
from telegram_notifier import TelegramNotifier


class DailyReporter:
    def __init__(self, config: Dict, withdrawal_monitor: WithdrawalMonitor = None, balance_monitor: BalanceMonitor = None):
        self.config = config
        
        # Use provided instances or create new ones
        self.withdrawal_monitor = withdrawal_monitor or WithdrawalMonitor(config)
        self.balance_monitor = balance_monitor or BalanceMonitor(config)
        
        self.telegram_notifier = TelegramNotifier(config)
        self.logger = logging.getLogger(__name__)
    
    def generate_daily_report(self, report_date: datetime = None) -> Dict:
        """Generate comprehensive daily report"""
        if report_date is None:
            report_date = datetime.now(timezone.utc)  # Current time
        
        try:
            # Calculate 24-hour window ending at report_date
            end_time = report_date
            start_time = end_time - timedelta(hours=24)
            
            self.logger.info(f"Generating daily report for 24-hour period: {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            
            # Get withdrawal statistics for the 24-hour period
            withdrawal_stats = self.withdrawal_monitor.get_daily_statistics_for_period(start_time, end_time)
            
            # Get current balance information
            balance_info = self.balance_monitor.check_all_balances()
            
            # Organize balance info by chain
            balance_by_chain = {}
            for balance in balance_info:
                if balance.chain not in balance_by_chain:
                    balance_by_chain[balance.chain] = []
                
                balance_by_chain[balance.chain].append({
                    'token_symbol': balance.token_symbol,
                    'token_address': balance.token_address,
                    'balance': balance.balance,
                    'threshold': balance.threshold,
                    'is_below_threshold': balance.is_below_threshold
                })
            
            # Add balance information to withdrawal stats
            for chain_name in withdrawal_stats:
                withdrawal_stats[chain_name]['balances'] = balance_by_chain.get(chain_name, [])
            
            # Add metadata
            withdrawal_stats['metadata'] = {
                'report_date': report_date.isoformat(),
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'total_chains': len(self.config['chains']),
                'report_type': 'daily'
            }
            
            return withdrawal_stats
            
        except Exception as e:
            self.logger.error(f"Error generating daily report: {str(e)}")
            return {'error': str(e)}
    
    def send_daily_report(self, report_date: datetime = None) -> bool:
        """Generate and send daily report via Telegram"""
        try:
            # Generate report
            report_data = self.generate_daily_report(report_date)
            
            if 'error' in report_data:
                self.logger.error(f"Failed to generate report: {report_data['error']}")
                return False
            
            # Send via Telegram
            success = self.telegram_notifier.send_daily_report(report_data)
            
            if success:
                self.logger.info("Daily report sent successfully")
            else:
                self.logger.error("Failed to send daily report")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error sending daily report: {str(e)}")
            return False
    
    def generate_weekly_summary(self, end_date: datetime = None) -> Dict:
        """Generate weekly summary report"""
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        
        start_date = end_date - timedelta(days=7)
        
        try:
            self.logger.info(f"Generating weekly summary from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            
            weekly_data = {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': 7
                },
                'chains': {},
                'totals': {
                    'successful_withdrawals': 0,
                    'failed_withdrawals': 0,
                    'total_withdrawals': 0
                }
            }
            
            # Collect data for each day
            for i in range(7):
                current_date = start_date + timedelta(days=i)
                daily_stats = self.withdrawal_monitor.get_daily_statistics(current_date)
                
                for chain_name, chain_data in daily_stats.items():
                    if chain_name not in weekly_data['chains']:
                        weekly_data['chains'][chain_name] = {
                            'successful_withdrawals': 0,
                            'failed_withdrawals': 0,
                            'total_withdrawals': 0,
                            'daily_breakdown': []
                        }
                    
                    # Add to chain totals
                    weekly_data['chains'][chain_name]['successful_withdrawals'] += chain_data.get('successful_withdrawals', 0)
                    weekly_data['chains'][chain_name]['failed_withdrawals'] += chain_data.get('failed_withdrawals', 0)
                    weekly_data['chains'][chain_name]['total_withdrawals'] += chain_data.get('total_withdrawals', 0)
                    
                    # Add daily breakdown
                    weekly_data['chains'][chain_name]['daily_breakdown'].append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'successful': chain_data.get('successful_withdrawals', 0),
                        'failed': chain_data.get('failed_withdrawals', 0)
                    })
                    
                    # Add to overall totals
                    weekly_data['totals']['successful_withdrawals'] += chain_data.get('successful_withdrawals', 0)
                    weekly_data['totals']['failed_withdrawals'] += chain_data.get('failed_withdrawals', 0)
                    weekly_data['totals']['total_withdrawals'] += chain_data.get('total_withdrawals', 0)
            
            # Calculate success rate
            total_withdrawals = weekly_data['totals']['total_withdrawals']
            if total_withdrawals > 0:
                success_rate = (weekly_data['totals']['successful_withdrawals'] / total_withdrawals) * 100
                weekly_data['totals']['success_rate'] = round(success_rate, 2)
            else:
                weekly_data['totals']['success_rate'] = 0
            
            return weekly_data
            
        except Exception as e:
            self.logger.error(f"Error generating weekly summary: {str(e)}")
            return {'error': str(e)}
    
    def generate_balance_report(self) -> Dict:
        """Generate detailed balance report"""
        try:
            self.logger.info("Generating balance report")
            
            # Get current balances
            balance_info = self.balance_monitor.check_all_balances()
            
            # Get balance trends
            trends = self.balance_monitor.get_balance_trends(hours=24)
            
            report = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'chains': {},
                'summary': {
                    'total_balances_checked': len(balance_info),
                    'low_balances': 0,
                    'critical_balances': 0
                }
            }
            
            # Organize by chain
            for balance in balance_info:
                if balance.chain not in report['chains']:
                    report['chains'][balance.chain] = {
                        'name': self.config['chains'][balance.chain]['name'],
                        'balances': []
                    }
                
                # Check if balance is critical (below 50% of threshold)
                is_critical = balance.balance < (balance.threshold * 0.5)
                
                balance_data = {
                    'token_symbol': balance.token_symbol,
                    'token_address': balance.token_address,
                    'balance': balance.balance,
                    'threshold': balance.threshold,
                    'is_below_threshold': balance.is_below_threshold,
                    'is_critical': is_critical,
                    'status': 'CRITICAL' if is_critical else 'LOW' if balance.is_below_threshold else 'OK'
                }
                
                # Add trend data if available
                trend_key = f"{balance.chain}_{balance.token_symbol}"
                if 'trends' in trends and trend_key in trends['trends']:
                    trend_data = trends['trends'][trend_key]
                    balance_data['trend'] = {
                        'change': trend_data['change'],
                        'change_percent': trend_data['change_percent'],
                        'direction': trend_data['trend']
                    }
                
                report['chains'][balance.chain]['balances'].append(balance_data)
                
                # Update summary counts
                if balance.is_below_threshold:
                    report['summary']['low_balances'] += 1
                if is_critical:
                    report['summary']['critical_balances'] += 1
            
            return report
            
        except Exception as e:
            self.logger.error(f"Error generating balance report: {str(e)}")
            return {'error': str(e)}
    
    def run_daily_report(self):
        """Run the daily reporting process"""
        try:
            self.logger.info("Starting daily report generation...")
            
            # Generate and send daily report
            success = self.send_daily_report()
            
            if success:
                self.logger.info("Daily report process completed successfully")
            else:
                self.logger.error("Daily report process failed")
                
                # Send error notification
                try:
                    self.telegram_notifier.send_error_notification(
                        "Failed to generate or send daily report",
                        "DailyReporter"
                    )
                except Exception as notify_error:
                    self.logger.error(f"Failed to send error notification: {str(notify_error)}")
            
        except Exception as e:
            self.logger.error(f"Error in daily report process: {str(e)}")
            
            # Send error notification
            try:
                self.telegram_notifier.send_error_notification(
                    f"Daily report error: {str(e)}",
                    "DailyReporter"
                )
            except Exception as notify_error:
                self.logger.error(f"Failed to send error notification: {str(notify_error)}")
    
    def get_system_status(self) -> Dict:
        """Get reporting system status"""
        status = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'last_report_time': None,  # This would be tracked in a production system
            'report_schedule': self.config['monitoring']['report_time_utc'],
            'chains_monitored': list(self.config['chains'].keys())
        }
        
        return status