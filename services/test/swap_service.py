# services/swap_service.py
from web3 import Web3
import json
import time

class SwapService:
    def __init__(self, rpc_url):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.router_address = "0xC532a74256D3Db42D0Bf7a0400fEFDbad7694008"
        
        # Load Uniswap Router ABI
        with open('abis/uniswap_router.json') as f:
            self.router_abi = json.load(f)
        
        # Load ERC-20 ABI
        self.erc20_abi = json.loads('''[
            {"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},
            {"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},
            {"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"success","type":"bool"}],"type":"function"}
        ]''')
    
    def get_token_balance(self, token_address, wallet_address):
        """Get token balance for a wallet"""
        token_contract = self.w3.eth.contract(
            address=token_address,
            abi=self.erc20_abi
        )
        balance = token_contract.functions.balanceOf(wallet_address).call()
        return balance
    
    def approve_token(self, private_key, token_address, amount):
        """Approve Uniswap to spend tokens"""
        account = self.w3.eth.account.from_key(private_key)
        token_contract = self.w3.eth.contract(
            address=token_address,
            abi=self.erc20_abi
        )
        
        # Build approve transaction
        tx = token_contract.functions.approve(
            self.router_address,
            amount
        ).build_transaction({
            'from': account.address,
            'nonce': self.w3.eth.get_transaction_count(account.address),
            'gas': 100000,
            'gasPrice': self.w3.eth.gas_price,
        })
        
        # Sign and send
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for confirmation
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt.status == 1
    
    def swap_tokens(self, private_key, from_token, to_token, amount_in, slippage=1):
        """
        Swap tokens on Uniswap V2
        
        Args:
            private_key: Sender's private key
            from_token: Address of token to sell
            to_token: Address of token to buy
            amount_in: Amount to sell (in smallest unit)
            slippage: Max slippage percentage (default 1%)
        """
        account = self.w3.eth.account.from_key(private_key)
        
        # 1. Create router contract instance
        router = self.w3.eth.contract(
            address=self.router_address,
            abi=self.router_abi
        )
        
        # 2. Get token instances
        from_token_contract = self.w3.eth.contract(
            address=from_token,
            abi=self.erc20_abi
        )
        
        # 3. Check balance
        balance = from_token_contract.functions.balanceOf(account.address).call()
        if balance < amount_in:
            raise Exception(f"Insufficient balance. Have: {balance}, Need: {amount_in}")
        
        # 4. Calculate minimum amount out (with slippage)
        # For testing, we'll use a simple 1% minimum
        # In production, you'd get quote from Uniswap
        amount_out_min = int(amount_in * (100 - slippage) / 100)
        
        # 5. Define swap path
        path = [from_token, to_token]
        
        # 6. Set deadline (20 minutes from now)
        deadline = int(time.time()) + 1200
        
        # 7. Build swap transaction
        tx = router.functions.swapExactTokensForTokens(
            amount_in,
            amount_out_min,  # Minimum amount to receive
            path,
            account.address,  # Recipient of output tokens
            deadline
        ).build_transaction({
            'from': account.address,
            'nonce': self.w3.eth.get_transaction_count(account.address),
            'gas': 250000,
            'gasPrice': self.w3.eth.gas_price,
        })
        
        # 8. Sign and send
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for receipt
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {
            'success': receipt.status == 1,
            'tx_hash': tx_hash.hex(),
            'gas_used': receipt.gasUsed,
            'block_number': receipt.blockNumber,
        }