import os
from web3 import Web3, HTTPProvider
from web3.exceptions import TransactionNotFound
from dotenv import load_dotenv
import logging
from typing import Dict, Optional, Union, Any
from schemas.evm import BalanceRequest, TransactionRequest
from sqlalchemy.orm import Session

load_dotenv()


NETWORK_CONFIGS = {
    "sepolia": {
        "https_rpc_url": f"{os.getenv('SEPOLIA_RPC_URL')}/{os.getenv('INFURA_PROJECT_ID')}",
        "wss_url": f"{os.getenv('SEPOLIA_WS_URL')}/{os.getenv('INFURA_PROJECT_ID')}",
        "chainId":11155111,
    }
}
class InSoService:
    def __init__(self):
        self.erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function"
            }
        ]
        
        self.web3 = Web3(HTTPProvider(NETWORK_CONFIGS["sepolia"]["https_rpc_url"]))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to blockchain network")

    def get_token_balance(self, req: BalanceRequest, db: Session):
            """
            Get ERC20 token balance for a specific wallet
            
            Returns:
                Dictionary with token balance information
            """

            print("req inso:");
            print(req.model_dump_json());
            try:
                # Validate addresses
                if not all(self.w3.is_address(addr) for addr in [req.token_address, req.address]):
                    return {"success": False, "error": "Invalid address format"}
                
                # Create contract instance
                token_contract = self.w3.eth.contract(
                    address=self.w3.to_checksum_address(req.token_address),
                    abi=self.erc20_abi
                )
                
                # Get token information
                balance = token_contract.functions.balanceOf(
                    self.w3.to_checksum_address(req.address)
                ).call()
                
                decimals = token_contract.functions.decimals().call()
                symbol = token_contract.functions.symbol().call()
                
                # Calculate actual balance
                actual_balance = balance / (10 ** decimals)
                
                return {
                    "success": True,
                    "address": req.address,
                    "chain": "insoblok",
                    "token_address": req.token_address,
                    "balance": float(actual_balance),
                    "raw_balance": balance,
                    "decimals": decimals,
                    "symbol": symbol,
                    "updated_at": balance.updated_at.isoformat()
                }
                
            except Exception as e:
                self.logger.error(f"Error getting token balance: {str(e)}")
                return {"success": False, "error": str(e)}
    
    def send_token(
        self,
        token_address: str,
        to_address: str,
        amount: float,
        private_key: str,
        gas_limit: int = 100000,
        gas_price: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send ERC20 tokens to another address
        
        Args:
            token_address: ERC20 token contract address
            to_address: Recipient address
            amount: Amount to send
            private_key: Sender's private key
            gas_limit: Gas limit for transaction
            gas_price: Gas price in wei (optional)
            
        Returns:
            Dictionary with transaction information
        """
        try:
            # Validate addresses
            if not all(self.w3.is_address(addr) for addr in [token_address, to_address]):
                return {"success": False, "error": "Invalid address format"}
            
            # Get account from private key
            account = self.w3.eth.account.from_key(private_key)
            from_address = account.address
            
            # Create contract instance
            token_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=self.erc20_abi
            )
            
            # Get token decimals
            decimals = token_contract.functions.decimals().call()
            symbol = token_contract.functions.symbol().call()
            
            # Convert amount to token units
            amount_units = int(amount * (10 ** decimals))
            
            # Get current gas price if not specified
            if gas_price is None:
                gas_price = self.w3.eth.gas_price
            
            # Get nonce
            nonce = self.w3.eth.get_transaction_count(from_address)
            
            # Build transaction
            transaction = token_contract.functions.transfer(
                self.w3.to_checksum_address(to_address),
                amount_units
            ).build_transaction({
                'from': from_address,
                'nonce': nonce,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': self.w3.eth.chain_id
            })
            
            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key)
            
            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            self.logger.info(f"ERC20 Transaction sent: {tx_hash.hex()}")
            
            return {
                "success": True,
                "from_address": from_address,
                "to_address": to_address,
                "token_address": token_address,
                "amount": amount,
                "symbol": symbol,
                "tx_hash": tx_hash.hex(),
                "gas_price": gas_price,
                "gas_limit": gas_limit
            }
            
        except Exception as e:
            self.logger.error(f"Error sending ERC20 token: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """
        Get transaction status and details
        
        Args:
            tx_hash: Transaction hash to check
            
        Returns:
            Dictionary with transaction status and details
        """
        try:
            # Get transaction receipt
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            # Get transaction details
            transaction = self.w3.eth.get_transaction(tx_hash)
            
            # Determine status
            status = "confirmed" if receipt.status == 1 else "failed"
            
            # Get block timestamp if available
            block_timestamp = None
            if receipt.blockNumber:
                block = self.w3.eth.get_block(receipt.blockNumber)
                block_timestamp = block.timestamp
            
            result = {
                "success": True,
                "tx_hash": tx_hash,
                "status": status,
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
                "cumulative_gas_used": receipt.cumulativeGasUsed,
                "from_address": receipt.from_address if hasattr(receipt, 'from_address') else transaction['from'],
                "to_address": receipt.to_address if hasattr(receipt, 'to_address') else transaction['to'],
                "value": transaction.value,
                "gas_price": transaction.gasPrice,
                "nonce": transaction.nonce,
                "block_timestamp": block_timestamp,
                "confirmations": self.w3.eth.block_number - receipt.blockNumber if receipt.blockNumber else 0
            }
            
            # Check if it's a token transfer
            if transaction.to and transaction.input and len(transaction.input) > 2:
                result["is_token_transfer"] = True
                result["input_data"] = transaction.input.hex()
            else:
                result["is_token_transfer"] = False
            
            return result
            
        except TransactionNotFound:
            return {"success": False, "error": "Transaction not found", "status": "not_found"}
        except Exception as e:
            self.logger.error(f"Error getting transaction status: {str(e)}")
            return {"success": False, "error": str(e)}