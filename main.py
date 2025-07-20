#!/usr/bin/env python3

import argparse
import logging
import schedule
import time
import yaml
import sys
import os
from datetime import datetime, timezone
from typing import Dict
from dotenv import load_dotenv

# Import our modules
from withdrawal_monitor import WithdrawalMonitor
from balance_monitor import BalanceMonitor
from daily_reporter import DailyReporter
from telegram_notifier import TelegramNotifier


def setup_logging(config: Dict) -> logging.Logger:
    """Set up logging configuration"""
    log_level = getattr(logging, config['logging']['level'].upper())
    log_file = config['logging']['file']
    max_file_size = config['logging']['max_file_size_mb'] * 1024 * 1024
    backup_count = config['logging']['backup_count']
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_file_size,
        backupCount=backup_count
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def load_config(config_path: str = 'config.yaml') -> Dict:
    """Load configuration from YAML file and substitute environment variables"""
    # Load environment variables from .env file
    load_dotenv()
    
    try:
        with open(config_path, 'r') as f:
            config_content = f.read()
        
        # Substitute environment variables
        config_content = os.path.expandvars(config_content)
        config = yaml.safe_load(config_content)
        return config
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_path}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing configuration file: {e}")
        sys.exit(1)


def validate_config(config: Dict) -> bool:
    """Validate configuration completeness"""
    required_sections = ['alchemy', 'telegram', 'exchange_contracts', 'tokens', 'chains']
    
    for section in required_sections:
        if section not in config:
            print(f"Error: Missing required configuration section: {section}")
            return False
    
    # Validate Alchemy API keys
    for chain in config['chains']:
        if chain not in config['alchemy']['api_keys']:
            print(f"Error: Missing Alchemy API key for chain: {chain}")
            return False
        
        if not config['alchemy']['api_keys'][chain] or config['alchemy']['api_keys'][chain].startswith('YOUR_') or config['alchemy']['api_keys'][chain].startswith('${'):
            print(f"Error: Please set a valid Alchemy API key for {chain} in your .env file")
            return False
    
    # Validate Telegram configuration
    if not config['telegram']['bot_token'] or config['telegram']['bot_token'].startswith('YOUR_') or config['telegram']['bot_token'].startswith('${'):
        print("Error: Please set a valid Telegram bot token in your .env file")
        return False
    
    if not config['telegram']['chat_id'] or config['telegram']['chat_id'].startswith('YOUR_') or config['telegram']['chat_id'].startswith('${'):
        print("Error: Please set a valid Telegram chat ID in your .env file")
        return False
    
    # Validate exchange contracts
    for chain in config['chains']:
        if chain not in config['exchange_contracts']:
            print(f"Error: Missing exchange contract address for chain: {chain}")
            return False
        
        if config['exchange_contracts'][chain].startswith('0x123'):
            print(f"Error: Please set a valid exchange contract address for {chain}")
            return False
    
    return True


class WithdrawalMonitoringSystem:
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.withdrawal_monitor = WithdrawalMonitor(config)
        self.balance_monitor = BalanceMonitor(config)
        self.telegram_notifier = TelegramNotifier(config)
        
        # Pass the same withdrawal_monitor instance to the daily reporter
        self.daily_reporter = DailyReporter(config, self.withdrawal_monitor, self.balance_monitor)
        
        # Track system status
        self.system_start_time = datetime.now(timezone.utc)
        self.last_withdrawal_check = None
        self.last_balance_check = None
        self.last_daily_report = None
    
    def run_withdrawal_monitoring(self):
        """Run withdrawal monitoring check"""
        try:
            self.logger.info("=== Starting Withdrawal Monitoring Check ===")
            self.withdrawal_monitor.run_single_check()
            self.last_withdrawal_check = datetime.now(timezone.utc)
            self.logger.info("=== Withdrawal Monitoring Check Complete ===")
        except Exception as e:
            self.logger.error(f"Error in withdrawal monitoring: {str(e)}")
    
    def run_balance_monitoring(self):
        """Run balance monitoring check"""
        try:
            self.logger.info("=== Starting Balance Monitoring Check ===")
            self.balance_monitor.run_balance_check()
            self.last_balance_check = datetime.now(timezone.utc)
            self.logger.info("=== Balance Monitoring Check Complete ===")
        except Exception as e:
            self.logger.error(f"Error in balance monitoring: {str(e)}")
    
    def run_daily_report(self):
        """Run daily report generation"""
        try:
            self.logger.info("=== Starting Daily Report Generation ===")
            self.daily_reporter.run_daily_report()
            self.last_daily_report = datetime.now(timezone.utc)
            self.logger.info("=== Daily Report Generation Complete ===")
        except Exception as e:
            self.logger.error(f"Error in daily report generation: {str(e)}")
    
    def test_system(self):
        """Test system connectivity and configuration"""
        self.logger.info("=== Testing System Connectivity ===")
        
        # Test Telegram connectivity
        if self.telegram_notifier.test_connection():
            self.logger.info("✅ Telegram bot connection successful")
        else:
            self.logger.error("❌ Telegram bot connection failed")
            return False
        
        # Test blockchain connections
        all_chains_connected = True
        for chain_name in self.config['chains']:
            if chain_name in self.withdrawal_monitor.blockchain_monitor.web3_instances:
                self.logger.info(f"✅ {chain_name} blockchain connection successful")
            else:
                self.logger.error(f"❌ {chain_name} blockchain connection failed")
                all_chains_connected = False
        
        if all_chains_connected:
            self.logger.info("✅ All blockchain connections successful")
        else:
            self.logger.error("❌ Some blockchain connections failed")
            return False
        
        # Send startup notification
        self.telegram_notifier.send_startup_notification()
        
        return True
    
    def _convert_utc_to_local_time(self, utc_time_str: str) -> str:
        """Convert UTC time string to local time for scheduling"""
        from datetime import datetime, timezone
        import time
        
        # Parse UTC time
        utc_hour, utc_minute = map(int, utc_time_str.split(':'))
        
        # Create UTC datetime for today
        utc_dt = datetime.now(timezone.utc).replace(hour=utc_hour, minute=utc_minute, second=0, microsecond=0)
        
        # Convert to local time
        local_dt = utc_dt.astimezone()
        
        # Format as HH:MM
        local_time_str = local_dt.strftime('%H:%M')
        
        self.logger.info(f"Daily report scheduled for {utc_time_str} UTC")
        
        return local_time_str
    
    def start_scheduled_monitoring(self):
        """Start the scheduled monitoring system"""
        # Schedule withdrawal monitoring
        polling_interval = self.config['monitoring']['polling_interval_minutes']
        schedule.every(polling_interval).minutes.do(self.run_withdrawal_monitoring)
        
        # Schedule balance monitoring
        balance_interval = self.config['monitoring']['balance_check_interval_minutes']
        schedule.every(balance_interval).minutes.do(self.run_balance_monitoring)
        
        # Schedule daily report - convert UTC to local time
        report_time_utc = self.config['monitoring']['report_time_utc']
        report_time_local = self._convert_utc_to_local_time(report_time_utc)
        schedule.every().day.at(report_time_local).do(self.run_daily_report)
        
        self.logger.info(f"Scheduled monitoring started:")
        self.logger.info(f"  - Withdrawal monitoring: every {polling_interval} minutes")
        self.logger.info(f"  - Balance monitoring: every {balance_interval} minutes")
        self.logger.info(f"  - Daily reports: at {report_time_utc} UTC")
        
        # Run initial checks
        self.logger.info("Running initial checks...")
        self.run_withdrawal_monitoring()
        self.run_balance_monitoring()
        
        # Main monitoring loop
        self.logger.info("Starting main monitoring loop...")
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                self.logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {str(e)}")
                time.sleep(60)  # Wait before retrying
    
    def get_system_status(self) -> Dict:
        """Get comprehensive system status"""
        status = {
            'system': {
                'start_time': self.system_start_time.isoformat(),
                'uptime_hours': (datetime.now(timezone.utc) - self.system_start_time).total_seconds() / 3600,
                'last_withdrawal_check': self.last_withdrawal_check.isoformat() if self.last_withdrawal_check else None,
                'last_balance_check': self.last_balance_check.isoformat() if self.last_balance_check else None,
                'last_daily_report': self.last_daily_report.isoformat() if self.last_daily_report else None
            },
            'withdrawal_monitor': self.withdrawal_monitor.get_system_status(),
            'balance_monitor': self.balance_monitor.get_system_status(),
            'daily_reporter': self.daily_reporter.get_system_status()
        }
        
        return status


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Cryptocurrency Withdrawal Monitoring System')
    parser.add_argument('--config', '-c', default='config.yaml', help='Configuration file path')
    parser.add_argument('--test', '-t', action='store_true', help='Test connectivity and exit')
    parser.add_argument('--run-once', '-o', action='store_true', help='Run monitoring checks once and exit')
    parser.add_argument('--daily-report', '-r', action='store_true', help='Generate daily report and exit')
    parser.add_argument('--status', '-s', action='store_true', help='Show system status and exit')
    
    args = parser.parse_args()
    
    # Load and validate configuration
    config = load_config(args.config)
    
    if not validate_config(config):
        sys.exit(1)
    
    # Setup logging
    logger = setup_logging(config)
    
    # Initialize system
    system = WithdrawalMonitoringSystem(config)
    
    # Handle different modes
    if args.test:
        logger.info("Testing system connectivity...")
        if system.test_system():
            logger.info("✅ All tests passed")
            sys.exit(0)
        else:
            logger.error("❌ Tests failed")
            sys.exit(1)
    
    elif args.run_once:
        logger.info("Running monitoring checks once...")
        system.run_withdrawal_monitoring()
        system.run_balance_monitoring()
        logger.info("Single run completed")
        sys.exit(0)
    
    elif args.daily_report:
        logger.info("Generating daily report...")
        system.run_daily_report()
        logger.info("Daily report completed")
        sys.exit(0)
    
    elif args.status:
        logger.info("System status:")
        status = system.get_system_status()
        import json
        print(json.dumps(status, indent=2))
        sys.exit(0)
    
    else:
        # Normal operation mode
        logger.info("Starting Withdrawal Monitoring System...")
        
        # Test system first
        if not system.test_system():
            logger.error("System test failed, exiting")
            sys.exit(1)
        
        # Start scheduled monitoring
        system.start_scheduled_monitoring()


if __name__ == "__main__":
    main()