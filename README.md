# inso-wallet
native insoblok wallet backend

## Local Development Setup

### 1. Create and activate virtual environment
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Linux/Mac
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root with the following variables:

#### For Local PostgreSQL Database:
```env
# Database Configuration (Local)
USE_LOCAL_DB=true
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=crypto_wallet

# Or use a full connection string instead:
# DATABASE_URL=postgresql://postgres:password@localhost:5432/crypto_wallet
```

#### For Google Cloud SQL (Production):
```env
# Database Configuration (Cloud)
USE_LOCAL_DB=false
INSTANCE_CONNECTION_NAME=your-project:region:instance-name
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=crypto_wallet
USE_PRIVATE_IP=false
```

#### Required API Keys:
```env
# Infura Configuration
INFURA_PROJECT_ID=your_infura_project_id
ETHEREUM_WS_URL=wss://mainnet.infura.io/ws/v3
ETHEREUM_RPC_URL=https://mainnet.infura.io/v3
SEPOLIA_WS_URL=wss://sepolia.infura.io/ws/v3
SEPOLIA_RPC_URL=https://sepolia.infura.io/v3

# Etherscan Configuration
ETHERSCAN_URL=https://api.etherscan.io/v2/api/
ETHERSCAN_API_KEY=your_etherscan_api_key

# Wallet Configuration
ADDRESS=your_wallet_address
PRIVATE_KEY=your_private_key

# Scheduler Configuration
TRANSACTION_STATUS_UPDATE_PERIOD_SECONDS=30

# Google Cloud Services (optional - only needed for production)
# USE_CLOUD_DB=false  # Set to true to use Google Cloud SQL instead of local database
# USE_GCLOUD_LOGGING=false  # Set to true to use Google Cloud Logging

# Notification Service Configuration (optional)
ENABLE_NOTIFICATIONS=true  # Set to false to disable all notifications
NOTIFICATION_CHANNELS=webhook  # Comma-separated: webhook,email,sms,push

# Webhook Configuration (recommended for custom integrations)
WEBHOOK_URL=https://your-webhook-endpoint.com/notify
WEBHOOK_SECRET=your_webhook_secret_key

# Email Configuration (optional)
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=your_email@gmail.com
# SMTP_PASSWORD=your_app_password
# SMTP_FROM_EMAIL=noreply@yourdomain.com

# SMS Configuration (optional - Twilio example)
# SMS_PROVIDER=twilio
# SMS_API_KEY=your_twilio_account_sid
# SMS_API_SECRET=your_twilio_auth_token
# SMS_FROM_NUMBER=+1234567890

# Push Notification Configuration (optional - Firebase example)
# PUSH_NOTIFICATION_SERVICE=firebase
# PUSH_API_KEY=your_firebase_server_key
```

### 4. Create the database (if using local PostgreSQL)
```sql
CREATE DATABASE crypto_wallet;
```

### 5. Run the application
```bash
# Using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port=8080 --reload

# Or use the provided scripts:
# Windows:
run_local.bat
# PowerShell:
.\run_local.ps1
```

The API will be available at: `http://localhost:8080`
API documentation: `http://localhost:8080/docs`

## Features

### Receiving Module
The receiving module automatically detects incoming transactions (native tokens and ERC20) to monitored addresses:
- **Automatic Detection**: Monitors new blocks for incoming transactions
- **Native & ERC20 Support**: Detects both native tokens (ETH) and ERC20 tokens
- **Notifications**: Automatically sends notifications when funds are received
- **API Endpoints**: 
  - `POST /receiving/monitor` - Add address to monitor
  - `GET /receiving/monitor` - Get monitored addresses
  - `POST /receiving/check` - Manually check address for incoming transactions
  - `GET /receiving/incoming/{address}` - Get all incoming transactions for an address

See [RECEIVING_MODULE.md](RECEIVING_MODULE.md) for detailed documentation.

### Notification Service
The notification service sends alerts when transactions succeed:
- **Multiple Channels**: Webhook, Email, SMS, Push notifications
- **Configurable**: Enable/disable via environment variables
- **Automatic**: Triggered when transactions are confirmed

See [NOTIFICATION_SETUP.md](NOTIFICATION_SETUP.md) for setup instructions.


RRC - 
VTO - capture image not work
Profile - social icons not shown on the top
Reaction - not shown
Tastescore - not worked
live stream - remove old live streams 