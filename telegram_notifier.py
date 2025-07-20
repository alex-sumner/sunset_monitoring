import logging
import requests
import time
from typing import Dict, List, Optional
from datetime import datetime, timezone
from blockchain_monitor import Transaction, BalanceInfo


class TelegramNotifier:
    def __init__(self, config: Dict):
        self.config = config
        self.bot_token = config['telegram']['bot_token']
        self.chat_id = config['telegram']['chat_id']
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.logger = logging.getLogger(__name__)
        
        # Rate limiting for notifications
        self.last_balance_alerts = {}  # Track last alert time for each token
        self.alert_cooldown_minutes = 60  # Don't spam balance alerts
        
    def send_message(self, message: str, parse_mode: str = "Markdown") -> bool:
        """Send a message to the configured Telegram chat"""
        url = f"{self.base_url}/sendMessage"
        
        payload = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': parse_mode,
            'disable_web_page_preview': True
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if result.get('ok'):
                self.logger.info("Telegram message sent successfully")
                return True
            else:
                self.logger.error(f"Telegram API error: {result.get('description', 'Unknown error')}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to send Telegram message: {str(e)}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error sending Telegram message: {str(e)}")
            return False
    
    def send_failed_withdrawal_alert(self, transaction: Transaction) -> bool:
        """Send alert for failed withdrawal transaction"""
        chain_name = self.config['chains'][transaction.chain]['name']
        
        # Format the amount if available
        amount_str = ""
        if 'amount' in transaction.decoded_params and transaction.decoded_params['amount']:
            amount = transaction.decoded_params['amount']
            # Convert from wei to readable format (assuming 18 decimals)
            amount_readable = amount / (10 ** 18)
            amount_str = f"\n💰 *Amount:* {amount_readable:,.6f}"
        
        # Format trader address if available
        trader_str = ""
        if 'trader' in transaction.decoded_params and transaction.decoded_params['trader']:
            trader = transaction.decoded_params['trader']
            trader_str = f"\n👤 *Trader:* `{trader}`"
        
        # Format withdrawal ID if available
        id_str = ""
        if 'id' in transaction.decoded_params and transaction.decoded_params['id']:
            withdrawal_id = transaction.decoded_params['id']
            id_str = f"\n🆔 *Withdrawal ID:* {withdrawal_id}"
        
        message = f"""🚨 *FAILED WITHDRAWAL DETECTED* 🚨

⛓️ *Chain:* {chain_name}
📄 *Contract:* `{transaction.contract_address}`
🔧 *Function:* `{transaction.function_name}`
🧾 *Transaction:* `{transaction.hash}`
📊 *Block:* {transaction.block_number}
⏰ *Time:* {transaction.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
⛽ *Gas Used:* {transaction.gas_used:,}{amount_str}{trader_str}{id_str}

🔍 *View Transaction:* [Block Explorer]({transaction.explorer_url})

⚠️ *Action Required:* Please investigate this failed withdrawal immediately."""
        
        return self.send_message(message)
    
    def send_low_balance_alert(self, balance_info: BalanceInfo) -> bool:
        """Send alert for low balance"""
        # Check rate limiting
        alert_key = f"{balance_info.chain}_{balance_info.token_symbol}"
        current_time = datetime.now(timezone.utc)
        
        if alert_key in self.last_balance_alerts:
            time_diff = (current_time - self.last_balance_alerts[alert_key]).total_seconds() / 60
            if time_diff < self.alert_cooldown_minutes:
                self.logger.info(f"Skipping low balance alert for {alert_key} due to rate limiting")
                return False
        
        # Update last alert time
        self.last_balance_alerts[alert_key] = current_time
        
        chain_name = self.config['chains'][balance_info.chain]['name']
        
        # Format balance without decimal places
        balance_str = f"{balance_info.balance:,.0f}"
        threshold_str = f"{balance_info.threshold:,.0f}"
        
        message = f"""🔴 *LOW BALANCE ALERT* 🔴

⛓️ *Chain:* {chain_name}
📄 *Contract:* `{balance_info.contract_address}`
🪙 *Token:* {balance_info.token_symbol}
💰 *Current Balance:* {balance_str} {balance_info.token_symbol}
⚠️ *Threshold:* {threshold_str} {balance_info.token_symbol}
📉 *Status:* Below threshold

🔍 *View Contract:* [Block Explorer]({balance_info.explorer_url})"""
        
        return self.send_message(message)
    
    def send_daily_report(self, report_data: Dict) -> bool:
        """Send daily summary report"""
        report_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        message = f"""📊 *DAILY WITHDRAWAL REPORT* 📊
📅 *Date:* {report_date}

"""
        
        total_successful = 0
        total_failed = 0
        
        # Process each chain's data
        for chain_name, chain_data in report_data.items():
            if chain_name == 'metadata':
                continue
                
            chain_display_name = self.config['chains'][chain_name]['name']
            successful_count = chain_data.get('successful_withdrawals', 0)
            failed_count = chain_data.get('failed_withdrawals', 0)
            
            total_successful += successful_count
            total_failed += failed_count
            
            message += f"*{chain_display_name}*\n"
            message += f"Successful: {successful_count}\n"
            message += f"Failed: {failed_count}\n"
            
            # Add failed transaction details if any
            if failed_count > 0 and 'failed_transactions' in chain_data:
                message += "Failed transactions:\n"
                for tx in chain_data['failed_transactions'][:5]:  # Limit to 5 for readability
                    message += f"  • `{tx['hash'][:10]}...` - Block {tx['block_number']}\n"
                if len(chain_data['failed_transactions']) > 5:
                    message += f"  ... and {len(chain_data['failed_transactions']) - 5} more\n"
            
            message += "\n"
        
        # Add summary
        message += f"📈 *TOTAL SUMMARY*\n"
        message += f"✅ Total Successful: {total_successful}\n"
        message += f"❌ Total Failed: {total_failed}\n"
        
        # Add current balances
        message += "💰 *CURRENT BALANCES*\n"
        for chain_name, chain_data in report_data.items():
            if chain_name == 'metadata' or 'balances' not in chain_data:
                continue
                
            chain_display_name = self.config['chains'][chain_name]['name']
            message += f"*{chain_display_name}*\n"
            
            for balance in chain_data['balances']:
                balance_str = f"{balance['balance']:,.0f}"
                
                status_emoji = "🔴" if balance['is_below_threshold'] else "🟢"
                message += f"  {status_emoji} {balance['token_symbol']}: {balance_str}\n"
            
            message += "\n"
        
        # Add timestamp
        message += f"⏰ *Generated:* {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        return self.send_message(message)
    
    def send_startup_notification(self) -> bool:
        """Send notification when the monitoring system starts"""
        message = f"""🚀 *WITHDRAWAL MONITORING SYSTEM STARTED*

⏰ *Started at:* {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

🔍 *Monitoring:*
• Failed withdrawal transactions
• Low balance alerts
• Daily reporting

📊 *Configuration:*
• Polling interval: {self.config['monitoring']['polling_interval_minutes']} minutes
• Balance check interval: {self.config['monitoring']['balance_check_interval_minutes']} minutes
• Chains monitored: {len(self.config['chains'])}

✅ System is now actively monitoring all configured chains."""
        
        return self.send_message(message)
    
    def send_error_notification(self, error_message: str, component: str = "System") -> bool:
        """Send notification for system errors"""
        message = f"""⚠️ *SYSTEM ERROR ALERT* ⚠️

🔧 *Component:* {component}
⏰ *Time:* {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

❌ *Error:* {error_message}

🔍 Please check the logs for more details."""
        
        return self.send_message(message)
    
    def test_connection(self) -> bool:
        """Test the Telegram bot connection"""
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            if result.get('ok'):
                bot_info = result.get('result', {})
                self.logger.info(f"Telegram bot connected successfully: @{bot_info.get('username', 'unknown')}")
                return True
            else:
                self.logger.error(f"Telegram bot test failed: {result.get('description', 'Unknown error')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Telegram bot connection test failed: {str(e)}")
            return False