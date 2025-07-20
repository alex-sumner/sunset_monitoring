import logging
import time
import functools
import json
import os
from typing import Callable, Any, Dict, Optional
from datetime import datetime, timezone


def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 2.0, 
                      exceptions: tuple = (Exception,)) -> Callable:
    """Decorator to retry functions with exponential backoff"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger = logging.getLogger(func.__module__)
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Function {func.__name__} failed after {max_retries} attempts: {str(e)}")
                        raise
                    
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries}), "
                                 f"retrying in {wait_time:.1f}s: {str(e)}")
                    time.sleep(wait_time)
            
            return None
        return wrapper
    return decorator


def safe_execute(func: Callable, *args, **kwargs) -> tuple[bool, Any]:
    """Safely execute a function and return (success, result)"""
    try:
        result = func(*args, **kwargs)
        return True, result
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error executing {func.__name__}: {str(e)}")
        return False, str(e)


class DataStore:
    """Simple JSON-based data store for persistence"""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.logger = logging.getLogger(__name__)
    
    def save(self, data: Dict) -> bool:
        """Save data to file"""
        try:
            # Add timestamp
            data['_timestamp'] = datetime.now(timezone.utc).isoformat()
            
            with open(self.filename, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
        except Exception as e:
            self.logger.error(f"Error saving data to {self.filename}: {str(e)}")
            return False
    
    def load(self) -> Optional[Dict]:
        """Load data from file"""
        try:
            if not os.path.exists(self.filename):
                return None
            
            with open(self.filename, 'r') as f:
                data = json.load(f)
            
            return data
        except Exception as e:
            self.logger.error(f"Error loading data from {self.filename}: {str(e)}")
            return None
    
    def exists(self) -> bool:
        """Check if data file exists"""
        return os.path.exists(self.filename)


class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, max_calls: int, time_window: float):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def is_allowed(self) -> bool:
        """Check if a call is allowed under rate limits"""
        now = time.time()
        
        # Remove old calls outside the time window
        self.calls = [call_time for call_time in self.calls if now - call_time < self.time_window]
        
        # Check if we can make another call
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        
        return False
    
    def wait_time(self) -> float:
        """Get the time to wait before next call is allowed"""
        if not self.calls:
            return 0.0
        
        oldest_call = min(self.calls)
        wait_time = self.time_window - (time.time() - oldest_call)
        
        return max(0.0, wait_time)


class HealthChecker:
    """System health monitoring"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.health_data = DataStore('health_status.json')
    
    def check_system_health(self) -> Dict:
        """Perform comprehensive system health check"""
        health_status = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'overall_status': 'healthy',
            'components': {}
        }
        
        # Check disk space
        disk_usage = self._check_disk_space()
        health_status['components']['disk'] = disk_usage
        
        # Check memory usage
        memory_usage = self._check_memory_usage()
        health_status['components']['memory'] = memory_usage
        
        # Check log file size
        log_status = self._check_log_files()
        health_status['components']['logs'] = log_status
        
        # Check configuration
        config_status = self._check_configuration()
        health_status['components']['configuration'] = config_status
        
        # Determine overall status
        component_statuses = [comp['status'] for comp in health_status['components'].values()]
        if 'critical' in component_statuses:
            health_status['overall_status'] = 'critical'
        elif 'warning' in component_statuses:
            health_status['overall_status'] = 'warning'
        
        # Save health status
        self.health_data.save(health_status)
        
        return health_status
    
    def _check_disk_space(self) -> Dict:
        """Check available disk space"""
        try:
            import shutil
            
            total, used, free = shutil.disk_usage('.')
            free_percent = (free / total) * 100
            
            status = 'healthy'
            if free_percent < 5:
                status = 'critical'
            elif free_percent < 10:
                status = 'warning'
            
            return {
                'status': status,
                'free_space_gb': free // (1024**3),
                'free_percent': round(free_percent, 1),
                'total_space_gb': total // (1024**3)
            }
        except Exception as e:
            self.logger.error(f"Error checking disk space: {str(e)}")
            return {'status': 'unknown', 'error': str(e)}
    
    def _check_memory_usage(self) -> Dict:
        """Check memory usage"""
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            used_percent = memory.percent
            
            status = 'healthy'
            if used_percent > 90:
                status = 'critical'
            elif used_percent > 80:
                status = 'warning'
            
            return {
                'status': status,
                'used_percent': round(used_percent, 1),
                'available_gb': memory.available // (1024**3),
                'total_gb': memory.total // (1024**3)
            }
        except ImportError:
            # psutil not available, skip memory check
            return {'status': 'unknown', 'error': 'psutil not available'}
        except Exception as e:
            self.logger.error(f"Error checking memory usage: {str(e)}")
            return {'status': 'unknown', 'error': str(e)}
    
    def _check_log_files(self) -> Dict:
        """Check log file sizes"""
        try:
            log_file = self.config['logging']['file']
            max_size_mb = self.config['logging']['max_file_size_mb']
            
            if not os.path.exists(log_file):
                return {'status': 'healthy', 'file_size_mb': 0}
            
            file_size = os.path.getsize(log_file)
            file_size_mb = file_size / (1024 * 1024)
            
            status = 'healthy'
            if file_size_mb > max_size_mb * 0.9:
                status = 'warning'
            
            return {
                'status': status,
                'file_size_mb': round(file_size_mb, 1),
                'max_size_mb': max_size_mb
            }
        except Exception as e:
            self.logger.error(f"Error checking log files: {str(e)}")
            return {'status': 'unknown', 'error': str(e)}
    
    def _check_configuration(self) -> Dict:
        """Check configuration validity"""
        try:
            # Check for placeholder values
            issues = []
            
            # Check API keys
            for chain, api_key in self.config['alchemy']['api_keys'].items():
                if api_key.startswith('YOUR_'):
                    issues.append(f"Placeholder API key for {chain}")
            
            # Check Telegram config
            if self.config['telegram']['bot_token'].startswith('YOUR_'):
                issues.append("Placeholder Telegram bot token")
            
            if self.config['telegram']['chat_id'].startswith('YOUR_'):
                issues.append("Placeholder Telegram chat ID")
            
            # Check contract addresses
            for chain, address in self.config['exchange_contracts'].items():
                if address.startswith('0x123'):
                    issues.append(f"Placeholder contract address for {chain}")
            
            status = 'critical' if issues else 'healthy'
            
            return {
                'status': status,
                'issues': issues
            }
        except Exception as e:
            self.logger.error(f"Error checking configuration: {str(e)}")
            return {'status': 'unknown', 'error': str(e)}


def format_amount(amount: float, decimals: int = 18) -> str:
    """Format token amount for display"""
    if amount == 0:
        return "0"
    
    # Convert from wei if needed
    if amount > 1e15:  # Likely in wei
        amount = amount / (10 ** decimals)
    
    if amount >= 1e6:
        return f"{amount/1e6:.2f}M"
    elif amount >= 1e3:
        return f"{amount/1e3:.2f}K"
    elif amount >= 1:
        return f"{amount:.2f}"
    else:
        return f"{amount:.6f}"


def validate_address(address: str) -> bool:
    """Validate Ethereum address format"""
    if not address.startswith('0x'):
        return False
    
    if len(address) != 42:
        return False
    
    try:
        int(address[2:], 16)
        return True
    except ValueError:
        return False


def get_explorer_url(chain: str, tx_hash: str = None, address: str = None) -> str:
    """Get block explorer URL for transaction or address"""
    explorers = {
        'ethereum': 'https://etherscan.io',
        'arbitrum': 'https://arbiscan.io',
        'base': 'https://basescan.org',
        'sonic': 'https://sonicscan.org',
        'blast': 'https://blastscan.io'
    }
    
    base_url = explorers.get(chain, 'https://etherscan.io')
    
    if tx_hash:
        return f"{base_url}/tx/{tx_hash}"
    elif address:
        return f"{base_url}/address/{address}"
    else:
        return base_url


def truncate_hash(hash_str: str, length: int = 10) -> str:
    """Truncate hash for display"""
    if len(hash_str) <= length:
        return hash_str
    
    return f"{hash_str[:length]}...{hash_str[-6:]}"


class SystemMonitor:
    """Monitor system performance and resource usage"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.start_time = time.time()
    
    def get_uptime(self) -> float:
        """Get system uptime in hours"""
        return (time.time() - self.start_time) / 3600
    
    def log_performance_metrics(self):
        """Log current performance metrics"""
        try:
            import psutil
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('.')
            
            self.logger.info(f"Performance metrics - CPU: {cpu_percent}%, "
                           f"Memory: {memory.percent}%, "
                           f"Disk: {(disk.used/disk.total)*100:.1f}%")
            
        except ImportError:
            self.logger.debug("psutil not available, skipping performance metrics")
        except Exception as e:
            self.logger.error(f"Error logging performance metrics: {str(e)}")