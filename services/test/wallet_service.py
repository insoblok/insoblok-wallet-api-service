# services/wallet_service.py
from web3 import Web3
from eth_account import Account
import secrets
from services.config.config import SEPOLIA_RPC

class WalletService:
    def __init__(self, rpc_url):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
    def create_wallet(self):
        """Create new Ethereum wallet"""
        # Generate private key
        private_key = "0x" + secrets.token_hex(32)
        
        # Create account
        account = Account.from_key(private_key)
        
        return {
            'address': account.address,
            'private_key': private_key,  # Store securely in real app
            'public_key': account.key.public_key.to_hex(),
        }
    
    def get_balance(self, address):
        """Get ETH balance"""
        balance_wei = self.w3.eth.get_balance(address)
        balance_eth = self.w3.from_wei(balance_wei, 'ether')
        return float(balance_eth)

# Create test wallets
wallet_service = WalletService(SEPOLIA_RPC)

# Create 2 wallets for testing
wallet1 = wallet_service.create_wallet()
wallet2 = wallet_service.create_wallet()

print(f"Wallet 1: {wallet1['address']}")
print(f"Wallet 2: {wallet2['address']}")