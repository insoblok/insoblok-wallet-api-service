# config.py
import os

SEPOLIA_CONFIG = {
    'RPC_URL': f'https://sepolia.infura.io/v3/{os.getenv("INFURA_PROJECT_ID")}',  # Get from infura.io
    'CHAIN_ID': 11155111,
    'NETWORK_NAME': 'Sepolia Testnet',
    'EXPLORER_URL': 'https://sepolia.etherscan.io',
    'NATIVE_SYMBOL': 'ETH',
}

# Or use free alternatives:
SEPOLIA_RPC_ALTERNATIVES = [
    'https://rpc.sepolia.org',  # Free
    'https://sepolia.drpc.org',  # Free
    'https://ethereum-sepolia.publicnode.com',  # Free
]

# Default SEPOLIA RPC URL (uses first free alternative)
SEPOLIA_RPC = SEPOLIA_RPC_ALTERNATIVES[0]