# Cryptocurrency Withdrawal Monitoring System

Monitoring cryptocurrency withdrawal transactions and contract balances across multiple EVM-compatible blockchains using Alchemy APIs and Telegram notifications.

## Features

- **Real-time Withdrawal Monitoring**: Detects failed `withdraw` function calls within 30 minutes
- **Multi-chain Support**: Monitors Ethereum, Arbitrum, Base, Sonic, and Blast networks
- **Balance Monitoring**: Tracks contract token balances and sends low balance alerts
- **Daily Reporting**: Generates comprehensive daily reports via Telegram
- **Telegram Integration**: Sends real-time alerts and reports to configured chat
- **Robust Error Handling**: Includes retry mechanisms and comprehensive logging
- **Retrieve Ethereum signer addresses fronm AWS KMS public keys**: `address_from_key.py`

## Prerequisites

- Python 3.8 or higher
- Alchemy API keys for each supported blockchain
- Telegram bot token and chat ID
- Exchange contract addresses for each chain

## Installation

1. Clone or download the project files
2. Install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

## Configuration

### 1. Create Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Create a new bot with `/newbot`
3. Save the bot token from BotFather
4. Add the bot to your monitoring chat/group
5. Get your chat ID by messaging [@userinfobot](https://t.me/userinfobot)

### 2. Get Alchemy API Keys

1. Sign up at [Alchemy](https://www.alchemy.com/)
2. Create apps for each blockchain:
   - Ethereum Mainnet
   - Arbitrum One
   - Base
   - Sonic
   - Blast
3. Copy the API keys from each app

### 3. Configure Environment Variables

**For security, sensitive credentials are stored in environment variables:**

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your actual credentials:
   ```bash
   # Alchemy API Configuration
   # Get your API key from https://www.alchemy.com/
   ALCHEMY_API_KEY=your_actual_alchemy_api_key_here

   # Telegram Bot Configuration
   # Create a bot with @BotFather on Telegram to get these values
   TELEGRAM_BOT_TOKEN=your_actual_telegram_bot_token_here
   TELEGRAM_CHAT_ID=your_actual_telegram_chat_id_here
   ```

3. Update exchange contract addresses in `config.yaml`:
   ```yaml
   # Replace with your actual exchange contract addresses
   exchange_contracts:
     ethereum: "0xYourEthereumExchangeContractAddress"
     arbitrum: "0xYourArbitrumExchangeContractAddress"
     base: "0xYourBaseExchangeContractAddress"
     sonic: "0xYourSonicExchangeContractAddress"
     blast: "0xYourBlastExchangeContractAddress"
   ```

**⚠️ Security Note**: 
- Never commit the `.env` file to version control
- The `.env` file contains your real API keys and should be kept private
- The `.env.example` file shows the required format with placeholder values

## Usage

### Test the System

Before running the monitoring system, test the configuration:

```bash
python main.py --test
```

This will:
- Test Telegram bot connectivity
- Test blockchain connections
- Send a test startup notification

### Run Once

To run monitoring checks once without scheduling:

```bash
python main.py --run-once
```

### Generate Daily Report

To generate and send a daily report immediately:

```bash
python main.py --daily-report
```

### Start Monitoring

To start the full monitoring system:

```bash
python main.py
```

This will:
- Run withdrawal monitoring every 10 minutes
- Run balance monitoring every hour
- Generate daily reports at 00:00 UTC
- Continue running until stopped

### Command Line Options

```bash
python main.py [OPTIONS]

Options:
  -c, --config FILE     Configuration file path (default: config.yaml)
  -t, --test           Test connectivity and exit
  -o, --run-once       Run monitoring checks once and exit
  -r, --daily-report   Generate daily report and exit
  -s, --status         Show system status and exit
  -h, --help           Show help message
```

## Monitoring Schedule

By default, the system runs:
- **Withdrawal monitoring**: Every 10 minutes
- **Balance monitoring**: Every hour
- **Daily reports**: At 00:00 UTC

You can modify these intervals in `config.yaml`:

```yaml
monitoring:
  polling_interval_minutes: 10
  balance_check_interval_minutes: 60
  report_time_utc: "00:00"
```

## Telegram Notifications

The system sends different types of notifications:

### 1. Failed Withdrawal Alerts
```
🚨 FAILED WITHDRAWAL DETECTED 🚨

⛓️ Chain: Ethereum Mainnet
📄 Contract: 0x1234...
🔧 Function: withdraw
🧾 Transaction: 0xabcd...
📊 Block: 12345678
⏰ Time: 2024-01-15 10:30:00 UTC
⛽ Gas Used: 85,000
💰 Amount: 1,000.000000
👤 Trader: 0x5678...
🆔 Withdrawal ID: 42

🔍 View Transaction: [Block Explorer](https://etherscan.io/tx/0xabcd...)

⚠️ Action Required: Please investigate this failed withdrawal immediately.
```

### 2. Low Balance Alerts
```
🔴 LOW BALANCE ALERT 🔴

⛓️ Chain: Ethereum Mainnet
📄 Contract: 0x1234...
🪙 Token: USDT
💰 Current Balance: 8,500.00 USDT
⚠️ Threshold: 10,000.00 USDT
📉 Status: Below threshold

🔍 View Contract: [Block Explorer](https://etherscan.io/address/0x1234...)

⚠️ Action Required: Please replenish the contract balance to ensure smooth operations.
```

### 3. Daily Reports
```
📊 DAILY WITHDRAWAL REPORT 📊
📅 Date: 2024-01-15

⛓️ Ethereum Mainnet
✅ Successful: 150
❌ Failed: 2
Failed transactions:
  • 0xabcd123... - Block 12345678
  • 0xdefg456... - Block 12345690

⛓️ Arbitrum One
✅ Successful: 89
❌ Failed: 0

📈 TOTAL SUMMARY
✅ Total Successful: 239
❌ Total Failed: 2
📊 Success Rate: 99.2%

💰 CURRENT BALANCES
⛓️ Ethereum Mainnet
  🟢 USDT: 25,000.00
  🟢 ETH: 15.500000

⛓️ Arbitrum One
  🔴 USDC: 8,500.00
  🟢 ETH: 2.100000

⏰ Generated: 2024-01-16 00:00:00 UTC
```

## Production Deployment

### Using systemd (Linux)

1. Create a systemd service file:

```bash
sudo nano /etc/systemd/system/withdrawal-monitor.service
```

```ini
[Unit]
Description=Cryptocurrency Withdrawal Monitor
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/sunset-monitoring
ExecStart=/usr/bin/python3 /path/to/sunset-monitoring/main.py
Restart=always
RestartSec=10
Environment=PYTHONPATH=/path/to/sunset-monitoring

[Install]
WantedBy=multi-user.target
```

2. Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable withdrawal-monitor.service
sudo systemctl start withdrawal-monitor.service
```

3. Check status:

```bash
sudo systemctl status withdrawal-monitor.service
```

### Using Docker

1. Create a Dockerfile:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

2. Build and run:

```bash
docker build -t withdrawal-monitor .
docker run -d --name withdrawal-monitor -v $(pwd)/config.yaml:/app/config.yaml withdrawal-monitor
```

## Logs

The system creates detailed logs in `withdrawal_monitor.log` (configurable in `config.yaml`). Log levels include:

- **INFO**: Normal operations, successful transactions
- **WARNING**: Low balances, failed transaction notifications
- **ERROR**: System errors, API failures
- **DEBUG**: Detailed debugging information

## Troubleshooting

### Common Issues

1. **Telegram Bot Not Working**
   - Verify bot token is correct
   - Ensure bot is added to the chat
   - Check chat ID is correct (negative for groups)

2. **Blockchain Connection Errors**
   - Verify Alchemy API keys are correct
   - Check network connectivity
   - Ensure Alchemy plan has sufficient compute units

3. **No Transactions Detected**
   - Verify exchange contract addresses are correct
   - Check if contracts have recent withdraw transactions
   - Ensure the withdraw function signature matches

4. **Balance Monitoring Issues**
   - Verify token contract addresses are correct
   - Check if tokens exist on specified chains
   - Ensure exchange contracts hold the tokens

### Getting Help

1. Check the log file for detailed error messages
2. Run the system with `--test` to diagnose connectivity issues
3. Use `--run-once` to test monitoring without scheduling
4. Enable DEBUG logging for more detailed information

## Security Considerations

- **Environment Variables**: Sensitive credentials are stored in `.env` file (not tracked by git)
- **API Key Security**: Never commit real API keys or bot tokens to version control
- **Regular Rotation**: Regularly rotate API keys and bot tokens for enhanced security
- **Access Control**: Implement proper access controls for the monitoring system
- **Log Monitoring**: Monitor system logs for suspicious activity
- **File Permissions**: Ensure `.env` file has restricted permissions (readable only by owner)
