from web3 import Web3, AsyncWeb3
from web3.middleware.signing import private_key_to_account
from web3.types import HexBytes
from web3.middleware import ExtraDataToPOAMiddleware
from web3.exceptions import ContractLogicError, TransactionNotFound
try:
    from web3.exceptions import ContractCustomError
except ImportError:
    # ContractCustomError may not be available in older web3.py versions
    # It's a subclass of ContractLogicError, so catching that will work
    ContractCustomError = ContractLogicError
from eth_account import Account
from sqlalchemy.orm import Session
from sqlalchemy import update, and_, func, func
from models import SwapHistory, TokenBalance, TxHistory
from services.notification import notify_transaction_success, notify_swap_success
from schemas.evm import BalanceRequest, TransactionRequest, QuoteRequest
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import SessionLocal
from fastapi import HTTPException
import os
import json
import asyncio
from datetime import datetime
import logging
from decimal import Decimal, ROUND_DOWN
from database import SessionLocal
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
load_dotenv()

# Only import Google Cloud logging if actually using it
USE_GCLOUD_LOGGING = os.getenv("USE_GCLOUD_LOGGING", "false").lower() == "true"
if USE_GCLOUD_LOGGING:
    import google.cloud.logging
    from google.cloud.logging_v2.handlers import CloudLoggingHandler
    from google.cloud.logging_v2.handlers import setup_logging


# Helper function to build RPC URLs safely
def _build_rpc_url(base_url_env: str, project_id_env: str = "INFURA_PROJECT_ID") -> str:
    """Build RPC URL from environment variables, handling None values"""
    base_url = os.getenv(base_url_env)
    project_id = os.getenv(project_id_env)
    
    if not base_url or not project_id:
        return None  # Return None if either is missing
    
    # Remove trailing slash from base_url if present
    base_url = base_url.rstrip('/')
    return f"{base_url}/{project_id}"

NETWORK_CONFIGS = {
    "ethereum": {
        "https_rpc_url": _build_rpc_url('ETHEREUM_RPC_URL'),
        "wss_url": _build_rpc_url('ETHEREUM_WS_URL'),
        "chainId": 1,
        "token_address": ""
    },
    "sepolia": {
        "https_rpc_url": _build_rpc_url('SEPOLIA_RPC_URL'),
        "wss_url": _build_rpc_url('SEPOLIA_WS_URL'),
        "chainId":11155111,
        "token_address": "",
    },
    "insoblok": {
        "https_rpc_url": _build_rpc_url('SEPOLIA_RPC_URL'),
        "wss_url": _build_rpc_url('SEPOLIA_WS_URL'),
        "chainId":11155111,
        "token_address": "0x724c5ECcB208992747E30ea6BB5E558F8bF770d5",
    }
}
CACHE_TTL_SECONDS = int(os.getenv("BALANCE_CACHE_TTL", "60"))

ERC20_ABI = [
    {"inputs": [], "stateMutability": "nonpayable", "type": "constructor"},
    {"inputs": [], "name": "ECDSAInvalidSignature", "type": "error"},
    {"inputs": [{"internalType": "uint256", "name": "length", "type": "uint256"}], "name": "ECDSAInvalidSignatureLength", "type": "error"},
    {"inputs": [{"internalType": "bytes32", "name": "s", "type": "bytes32"}], "name": "ECDSAInvalidSignatureS", "type": "error"},
    {"inputs": [
        {"internalType": "address", "name": "spender", "type": "address"},
        {"internalType": "uint256", "name": "allowance", "type": "uint256"},
        {"internalType": "uint256", "name": "needed", "type": "uint256"}],
     "name": "ERC20InsufficientAllowance", "type": "error"},
    {"inputs": [
        {"internalType": "address", "name": "sender", "type": "address"},
        {"internalType": "uint256", "name": "balance", "type": "uint256"},
        {"internalType": "uint256", "name": "needed", "type": "uint256"}],
     "name": "ERC20InsufficientBalance", "type": "error"},
    {"inputs": [{"internalType": "address", "name": "approver", "type": "address"}], "name": "ERC20InvalidApprover", "type": "error"},
    {"inputs": [{"internalType": "address", "name": "receiver", "type": "address"}], "name": "ERC20InvalidReceiver", "type": "error"},
    {"inputs": [{"internalType": "address", "name": "sender", "type": "address"}], "name": "ERC20InvalidSender", "type": "error"},
    {"inputs": [{"internalType": "address", "name": "spender", "type": "address"}], "name": "ERC20InvalidSpender", "type": "error"},
    {"inputs": [{"internalType": "uint256", "name": "deadline", "type": "uint256"}], "name": "ERC2612ExpiredSignature", "type": "error"},
    {"inputs": [
        {"internalType": "address", "name": "signer", "type": "address"},
        {"internalType": "address", "name": "owner", "type": "address"}],
     "name": "ERC2612InvalidSigner", "type": "error"},
    {"inputs": [
        {"internalType": "address", "name": "account", "type": "address"},
        {"internalType": "uint256", "name": "currentNonce", "type": "uint256"}],
     "name": "InvalidAccountNonce", "type": "error"},
    {"inputs": [], "name": "InvalidShortString", "type": "error"},
    {"inputs": [{"internalType": "address", "name": "owner", "type": "address"}], "name": "OwnableInvalidOwner", "type": "error"},
    {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "OwnableUnauthorizedAccount", "type": "error"},
    {"inputs": [{"internalType": "string", "name": "str", "type": "string"}], "name": "StringTooLong", "type": "error"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "spender", "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "value", "type": "uint256"}],
     "name": "Approval", "type": "event"},
    {"anonymous": False, "inputs": [], "name": "EIP712DomainChanged", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "address", "name": "previousOwner", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "newOwner", "type": "address"}],
     "name": "OwnershipTransferred", "type": "event"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "value", "type": "uint256"}],
     "name": "Transfer", "type": "event"},
    {"inputs": [], "name": "DOMAIN_SEPARATOR", "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [
        {"internalType": "address", "name": "owner", "type": "address"},
        {"internalType": "address", "name": "spender", "type": "address"}],
     "name": "allowance", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [
        {"internalType": "address", "name": "spender", "type": "address"},
        {"internalType": "uint256", "name": "value", "type": "uint256"}],
     "name": "approve", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "value", "type": "uint256"}], "name": "burn", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [
        {"internalType": "address", "name": "account", "type": "address"},
        {"internalType": "uint256", "name": "value", "type": "uint256"}],
     "name": "burnFrom", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "eip712Domain", "outputs": [
        {"internalType": "bytes1", "name": "fields", "type": "bytes1"},
        {"internalType": "string", "name": "name", "type": "string"},
        {"internalType": "string", "name": "version", "type": "string"},
        {"internalType": "uint256", "name": "chainId", "type": "uint256"},
        {"internalType": "address", "name": "verifyingContract", "type": "address"},
        {"internalType": "bytes32", "name": "salt", "type": "bytes32"},
        {"internalType": "uint256[]", "name": "extensions", "type": "uint256[]"}],"stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "name", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "owner", "type": "address"}], "name": "nonces", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "owner", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [
        {"internalType": "address", "name": "owner", "type": "address"},
        {"internalType": "address", "name": "spender", "type": "address"},
        {"internalType": "uint256", "name": "value", "type": "uint256"},
        {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        {"internalType": "uint8", "name": "v", "type": "uint8"},
        {"internalType": "bytes32", "name": "r", "type": "bytes32"},
        {"internalType": "bytes32", "name": "s", "type": "bytes32"}],
     "name": "permit", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "renounceOwnership", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "symbol", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalSupply", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [
        {"internalType": "address", "name": "to", "type": "address"},
        {"internalType": "uint256", "name": "value", "type": "uint256"}],
     "name": "transfer", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [
        {"internalType": "address", "name": "from", "type": "address"},
        {"internalType": "address", "name": "to", "type": "address"},
        {"internalType": "uint256", "name": "value", "type": "uint256"}],
     "name": "transferFrom", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "newOwner", "type": "address"}], "name": "transferOwnership", "outputs": [], "stateMutability": "nonpayable", "type": "function"}
]

# Initialize logging - use Google Cloud logging only if enabled, otherwise use standard logging
if USE_GCLOUD_LOGGING:
    try:
        client = google.cloud.logging.Client()
        
        def setup_gcloud_logging():
            """Setup logging for Google Cloud App Engine"""
            
            # Get the root logger
            logger = logging.getLogger()
            logger.setLevel(logging.INFO)
            
            # Clear existing handlers
            logger.handlers.clear()
            
            # Create Cloud Logging handler
            cloud_handler = CloudLoggingHandler(client)
            
            # Set formatter to output JSON that gcloud can parse
            formatter = logging.Formatter(
                '{"message": "%(message)s", "severity": "%(levelname)s", "timestamp": "%(asctime)s"}'
            )
            cloud_handler.setFormatter(formatter)
            
            # Add the handler to the logger
            logger.addHandler(cloud_handler)
            
            return logger
        logger = setup_gcloud_logging()
    except Exception as e:
        # Fallback to standard logging if Google Cloud logging fails
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to initialize Google Cloud logging: {e}. Using standard logging.")
else:
    # Use standard Python logging for local development
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

def log_info(message: str, **kwargs):
    """Log info message with additional context"""
    if kwargs:
        logger.info(f"{message} - {json.dumps(kwargs)}")
    else:
        logger.info(message)
def _get_w3(chain: str) -> Web3:
    rpc = NETWORK_CONFIGS[chain]["https_rpc_url"]
    if not rpc or rpc == "None" or "None" in rpc:
        raise HTTPException(
            status_code=500,
            detail=f"RPC endpoint not configured for chain '{chain}'. Please set {chain.upper()}_RPC_URL and INFURA_PROJECT_ID in your .env file."
        )
    # Validate URL format
    if not rpc.startswith(("http://", "https://", "ws://", "wss://")):
        raise HTTPException(
            status_code=500,
            detail=f"Invalid RPC URL format for chain '{chain}': {rpc}. URL must start with http://, https://, ws://, or wss://"
        )
    
    # Configure request kwargs to handle proxy issues
    # By default, bypass proxy for RPC calls to avoid authentication issues
    request_kwargs = {
        'timeout': 30,  # 30 second timeout for RPC calls
        'proxies': {
            'http': None,
            'https': None
        }
    }
    
    # Allow proxy configuration via environment variables if needed
    http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
    https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
    
    if http_proxy or https_proxy:
        # If proxy is explicitly configured, use it
        request_kwargs['proxies'] = {}
        if http_proxy:
            request_kwargs['proxies']['http'] = http_proxy
        if https_proxy:
            request_kwargs['proxies']['https'] = https_proxy
        
        # Handle proxy authentication if provided
        proxy_user = os.getenv('PROXY_USER') or os.getenv('proxy_user')
        proxy_pass = os.getenv('PROXY_PASS') or os.getenv('proxy_pass')
        if proxy_user and proxy_pass:
            # Reconstruct proxy URLs with authentication
            if http_proxy:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(http_proxy)
                http_proxy = urlunparse((
                    parsed.scheme,
                    f"{proxy_user}:{proxy_pass}@{parsed.netloc.split('@')[-1]}",
                    parsed.path, parsed.params, parsed.query, parsed.fragment
                ))
                request_kwargs['proxies']['http'] = http_proxy
            if https_proxy:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(https_proxy)
                https_proxy = urlunparse((
                    parsed.scheme,
                    f"{proxy_user}:{proxy_pass}@{parsed.netloc.split('@')[-1]}",
                    parsed.path, parsed.params, parsed.query, parsed.fragment
                ))
                request_kwargs['proxies']['https'] = https_proxy
    
    # Add timeout configuration to prevent hanging requests
    # request_kwargs includes timeout settings for HTTP requests
    return Web3(Web3.HTTPProvider(
        rpc,
        request_kwargs=request_kwargs
    ))

def public_key_to_address(public_key: str) -> str:
    """
    Convert a public key to an Ethereum address.
    
    Args:
        public_key: Public key in hex format (with or without 0x prefix)
                    Can be 64 bytes (128 hex chars) or 65 bytes (130 hex chars with 0x04 prefix)
    
    Returns:
        Ethereum address (checksummed)
    """
    try:
        # Remove 0x prefix if present
        if public_key.startswith("0x"):
            public_key = public_key[2:]
        
        # Convert hex string to bytes
        public_key_bytes = bytes.fromhex(public_key)
        
        # If it's 65 bytes (uncompressed with 0x04 prefix), remove the first byte
        if len(public_key_bytes) == 65:
            public_key_bytes = public_key_bytes[1:]
        
        # Hash with keccak256
        keccak_hash = Web3.keccak(public_key_bytes)
        
        # Take last 20 bytes (40 hex characters)
        address_bytes = keccak_hash[-20:]
        
        # Convert to hex and add 0x prefix
        address = "0x" + address_bytes.hex()
        
        # Return checksummed address
        return Web3.to_checksum_address(address)
    except Exception as e:
        logger.error(f"Error converting public key to address: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid public key format: {str(e)}"
        )

def get_balance(db: Session, req: BalanceRequest):
    """
    Get balance(s) for given BalanceRequest.
    - If req.chain is set (ethereum, bnb, etc) -> fetch one chain.
    - If req.chain == "" -> fetch balances across all SUPPORTED_CHAINS.
    """
    # Ensure logger is available
    if 'logger' not in globals():
        logger = logging.getLogger(__name__)
    
    try:
        # Validate chain exists in config
        if req.chain and req.chain not in NETWORK_CONFIGS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported chain '{req.chain}'. Supported chains: {list(NETWORK_CONFIGS.keys())}"
            )
        
        chains_to_check = [req.chain] if req.chain else list(NETWORK_CONFIGS.keys())
        results = []

        now = datetime.utcnow()
        w3_cache: dict[str, Web3] = {}

        for chain in chains_to_check:
            try:
                q = db.query(TokenBalance).filter(
                    and_(
                        TokenBalance.chain == chain,
                        TokenBalance.address == req.address
                    )
                )
                token_address = NETWORK_CONFIGS[chain]["token_address"]
                if token_address != "":
                    q = q.filter(TokenBalance.token_address == token_address)
                else:
                    q = q.filter(TokenBalance.token_address.is_(None))

                token_balance = q.first()

                # Serve from cache if fresh
                if token_balance and (now - token_balance.updated_at) < timedelta(seconds=CACHE_TTL_SECONDS):
                    results.append({
                        "address": token_balance.address,
                        "chain": token_balance.chain,
                        "token_address": token_balance.token_address,
                        "decimals": token_balance.decimals,
                        "balance": float(token_balance.balance),
                        "balance_raw": token_balance.balance_raw,
                        "updated_at": token_balance.updated_at.isoformat()
                    })
                    continue

                # Validate RPC URL is configured
                rpc_url = NETWORK_CONFIGS[chain].get("https_rpc_url")
                if not rpc_url or "None" in rpc_url:
                    logger.error(f"RPC URL not configured for chain '{chain}'. Please set INFURA_PROJECT_ID and RPC URLs in .env")
                    raise HTTPException(
                        status_code=500,
                        detail=f"RPC endpoint not configured for chain '{chain}'. Please configure INFURA_PROJECT_ID and RPC URLs."
                    )

                # Init web3 client if not cached
                if chain not in w3_cache:
                    w3_cache[chain] = _get_w3(chain=chain)
                w3 = w3_cache[chain]

                # Note: We skip is_connected() check because it makes a network call that can timeout
                # Instead, we'll catch errors during the actual RPC calls below

                try:
                    if token_address != "":
                        # ERC20 balance
                        contract = w3.eth.contract(
                            address=Web3.to_checksum_address(token_address),
                            abi=ERC20_ABI
                        )
                        balance_raw_int = contract.functions.balanceOf(
                            Web3.to_checksum_address(req.address)
                        ).call()
                        decimals = 18
                        balance_decimal = balance_raw_int / (10 ** decimals)
                        balance_raw = str(balance_raw_int)
                    else:
                        # Native coin balance
                        wei = w3.eth.get_balance(Web3.to_checksum_address(req.address))
                        balance_raw = str(int(wei))
                        balance_decimal = float(Web3.from_wei(wei, "ether"))
                except (ConnectionError, TimeoutError, Exception) as e:
                    error_msg = str(e)
                    logger.error(f"RPC error for chain '{chain}': {error_msg}")
                    
                    # Check for specific timeout/connection errors
                    if any(keyword in error_msg.lower() for keyword in ['timeout', 'connection', 'unavailable', 'refused', '503', '502', '504']):
                        raise HTTPException(
                            status_code=503,
                            detail=f"RPC endpoint for chain '{chain}' is temporarily unavailable. Please try again in 30 seconds."
                        )
                    # For other errors, still return 503 but with generic message
                    raise HTTPException(
                        status_code=503,
                        detail=f"RPC endpoint for chain '{chain}' is temporarily unavailable. Please try again in 30 seconds."
                    )

                # Upsert DB
                if token_balance:
                    token_balance.balance_raw = balance_raw
                    token_balance.balance = float(balance_decimal)
                    token_balance.updated_at = now
                else:
                    token_balance = TokenBalance(
                        chain=chain,
                        address=req.address,
                        token_address=token_address,
                        balance_raw=balance_raw,
                        balance=float(balance_decimal),
                        updated_at=now
                    )
                    db.add(token_balance)

                db.commit()
                db.refresh(token_balance)

                results.append({
                    "address": token_balance.address,
                    "chain": token_balance.chain,
                    "token_address": token_balance.token_address,
                    "balance": float(token_balance.balance),
                    "balance_raw": token_balance.balance_raw,
                    "updated_at": token_balance.updated_at.isoformat()
                })
            except HTTPException:
                # Re-raise HTTP exceptions
                raise
            except KeyError as e:
                logger.error(f"Configuration error for chain '{chain}': {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Configuration error for chain '{chain}': {str(e)}"
                )
            except Exception as e:
                logger.error(f"Error fetching balance for chain '{chain}': {str(e)}")
                # Continue to next chain instead of failing completely
                results.append({
                    "chain": chain,
                    "address": req.address,
                    "error": str(e)
                })
        
        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_balance: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

def send_transaction(db: Session, req: TransactionRequest):
    """
    Non-custodial send transaction.
    The frontend signs the tx and sends signed_raw_tx here.
    """

    print("req send_transaction:");
    print(req.model_dump_json());
    
    try:
        # Validate chain exists
        if req.chain not in NETWORK_CONFIGS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported chain '{req.chain}'. Supported chains: {list(NETWORK_CONFIGS.keys())}"
            )
        
        w3 = _get_w3(req.chain)
        
        # Note: We skip is_connected() check to avoid timeout issues
        # Errors will be caught during the actual transaction broadcast

        # Broadcast the signed tx to the network
        tx_hash = w3.eth.send_raw_transaction(req.signed_raw_tx)
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except (ValueError, ContractLogicError) as e:
        # Handle Web3 validation errors
        error_msg = str(e)
        if "insufficient funds" in error_msg.lower() or "balance" in error_msg.lower():
            logger.warning(f"Insufficient funds error: {error_msg}")
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient funds: {error_msg}"
            )
        raise HTTPException(
            status_code=400,
            detail=f"Transaction validation error: {error_msg}"
        )
    except Exception as e:
        # Handle RPC errors that come as dictionaries
        # Web3 sometimes wraps RPC errors, so check both the exception itself and its string representation
        error_dict = None
        error_code = None
        error_message = None
        
        # Check if exception is a dict
        if isinstance(e, dict):
            error_dict = e
            error_code = e.get('code', '')
            error_message = e.get('message', '')
            # Ensure we extract the message string, not the dict
            if not error_message:
                error_message = 'Unknown error'
        # Check if exception message contains dict-like structure
        elif hasattr(e, 'args') and len(e.args) > 0:
            # Sometimes Web3 wraps the error dict in args
            if isinstance(e.args[0], dict):
                error_dict = e.args[0]
                error_code = error_dict.get('code', '')
                error_message = error_dict.get('message', str(e))
            # Check if string representation contains dict
            elif isinstance(e.args[0], str) and '{' in str(e.args[0]):
                import json
                try:
                    # Try to parse as JSON if it looks like a dict string
                    error_dict = json.loads(e.args[0].replace("'", '"'))
                    error_code = error_dict.get('code', '')
                    error_message = error_dict.get('message', str(e))
                except:
                    error_message = str(e)
            else:
                error_message = str(e)
        else:
            error_message = str(e)
            # Try to extract dict from string representation
            error_str = str(e)
            if '{' in error_str and 'code' in error_str and 'message' in error_str:
                import re
                # Try to extract message from dict-like string
                message_match = re.search(r"'message':\s*['\"]([^'\"]+)['\"]", error_str)
                code_match = re.search(r"'code':\s*(-?\d+)", error_str)
                if message_match:
                    error_message = message_match.group(1)
                if code_match:
                    error_code = int(code_match.group(1))
        
        # Check for insufficient funds (code -32000 is common for this)
        # Also check if error_message is still a dict (shouldn't happen, but handle it)
        if isinstance(error_message, dict):
            error_message = error_message.get('message', str(error_message))
        
        if error_message and ('insufficient funds' in str(error_message).lower() or error_code == -32000):
            # Ensure error_message is a string
            error_msg_str = str(error_message) if not isinstance(error_message, str) else error_message
            logger.warning(f"Insufficient funds: {error_msg_str}")
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient funds: {error_msg_str}"
            )
        
        # Check for other client errors (only if we have error_message)
        if error_message:
            client_error_messages = [
                'nonce too low',
                'nonce too high',
                'invalid signature',
                'transaction underpriced',
                'replacement transaction underpriced',
                'already known',
                'gas required exceeds allowance'
            ]
            
            for client_error in client_error_messages:
                if client_error in error_message.lower():
                    logger.warning(f"Client error: {error_message}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Transaction error: {error_message}"
                    )
            
            # If we have error_dict, it's an RPC error
            if error_dict:
                logger.error(f"RPC error: {error_message} (code: {error_code})")
                raise HTTPException(
                    status_code=500,
                    detail=f"RPC error: {error_message}"
                )
        
        # Handle string-based errors
        error_msg = str(e)
        error_repr = repr(e)
        
        # Check for insufficient funds errors
        if 'insufficient funds' in error_msg.lower():
            logger.warning(f"Insufficient funds error: {error_msg}")
            # Try to extract message from dict-like string representation
            if 'message' in error_repr:
                import re
                match = re.search(r"'message':\s*'([^']+)'", error_repr)
                if match:
                    error_msg = match.group(1)
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient funds: {error_msg}"
            )
        
        # Check for other common blockchain errors that should be 400 (client errors)
        client_errors = [
            'nonce too low',
            'nonce too high',
            'invalid signature',
            'transaction underpriced',
            'replacement transaction underpriced',
            'already known',
            'gas required exceeds allowance'
        ]
        
        for client_error in client_errors:
            if client_error in error_msg.lower():
                logger.warning(f"Client error: {error_msg}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Transaction error: {error_msg}"
                )
        
        # All other errors are server errors
        logger.error(f"Error sending transaction: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send transaction: {error_msg}"
        )

    # Save transaction history (optional, metadata provided by frontend)
    # Convert HexBytes to hex string (already includes 0x prefix)
    tx_hash_str = tx_hash.hex() if hasattr(tx_hash, 'hex') else str(tx_hash)
    if not tx_hash_str.startswith('0x'):
        tx_hash_str = f"0x{tx_hash_str}"
    
    new_tx = TxHistory(
        from_address=req.from_address,
        to_address=req.to_address,
        token_symbol=req.token_symbol,
        amount=req.amount,
        tx_hash=tx_hash_str,
        status="pending",
        chain=req.chain
    )
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)

    return new_tx

def get_transaction(db: Session, tx_hash: str, chain: str):
    transaction = db.query(TxHistory).filter(TxHistory.tx_hash == tx_hash).first()
    w3 = _get_w3(chain)
    if transaction.status == "pending":
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt["status"] == 1:
                db.query(TxHistory).filter(TxHistory.tx_hash==tx_hash).update(
                    { "status": "success" }, synchronize_session=False
                )
                transaction.status = "success"
                db.commit()  # Commit before sending notification
                # Send notification to recipient
                try:
                    notify_transaction_success(transaction, transaction.to_address)
                except Exception as e:
                    logger.error(f"Error sending notification: {str(e)}")
            elif receipt["status"] == 0:
                db.query(TxHistory).filter(TxHistory.tx_hash==tx_hash).update(
                    { "status": "failed" }, synchronize_session=False
                )
                transaction.status = "failed"
            db.commit()
        except Exception as e:
            logger.warning(f"Error fetching transaction receipt: {str(e)}")
    print(transaction)
    return transaction

def get_quote(db: Session, req: QuoteRequest):
    w3 = _get_w3(req.chain)
    if not (w3.is_address(req.from_address) and w3.is_address(req.to)):
        raise HTTPException(400, "Invalid address")
    
    # Get token address from network config
    token_address = NETWORK_CONFIGS[req.chain].get("token_address", "")
    
    # Validate token_address if provided
    if not token_address:
        raise HTTPException(
            status_code=400,
            detail=f"No token address configured for chain '{req.chain}'. Please specify a token address."
        )
    
    if not w3.is_address(token_address):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid token address '{token_address}' for chain '{req.chain}'"
        )
    
    try:
        token = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=ERC20_ABI)
    except Exception as e:
        logger.error(f"Error creating token contract: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create token contract: {str(e)}"
        )

    # Get decimals
    try:
        decimals = token.functions.decimals().call()
    except Exception as e:
        logger.error(f"Error getting token decimals for {token_address} on {req.chain}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get token decimals. Token contract may not be valid or not deployed on {req.chain}: {str(e)}"
        )

    # Convert human amount to smallest unit on server for gas estimation
    # (safe: we do not sign here)
    amt = (Decimal(req.amount) * (Decimal(10) ** decimals)).to_integral_value(rounding=ROUND_DOWN)
    amount_wei = int(amt)

    # Check balance BEFORE attempting gas estimation to provide better error messages
    # For insoblok, check database balance (since INSO tokens are managed in DB, not on blockchain)
    # For other chains, check blockchain balance
    try:
        from_address_checksum = w3.to_checksum_address(req.from_address)
        
        if req.chain == "insoblok":
            # For insoblok, INSO balance is stored in database, not on blockchain
            # Use the SAME query logic as get_balance() to ensure consistency
            logger.info(f"=== get_quote balance check for insoblok ===")
            logger.info(f"Request from_address: {req.from_address}")
            logger.info(f"Request from_address (repr): {repr(req.from_address)}")
            logger.info(f"Token address from config: {token_address}")
            logger.info(f"Token address (repr): {repr(token_address)}")
            
            # Try exact match first (same as get_balance)
            q = db.query(TokenBalance).filter(
                and_(
                    TokenBalance.chain == "insoblok",
                    func.lower(TokenBalance.address) == req.from_address.lower().strip(),
                    func.lower(TokenBalance.token_address) == token_address.lower().strip()
                )
            )


            if token_address:
                q = q.filter(TokenBalance.token_address == token_address)
            else:
                q = q.filter(TokenBalance.token_address.is_(None))
            
            token_balance = q.first()
            logger.info(f"Exact match query result: {token_balance}")
            
            # If not found with exact match, try case-insensitive as fallback
            if not token_balance:
                logger.info("Exact match failed, trying case-insensitive...")
                from_address_normalized = req.from_address.lower().strip()
                token_address_normalized = token_address.lower().strip() if token_address else None
                
                logger.info(f"Normalized from_address: {from_address_normalized}")
                logger.info(f"Normalized token_address: {token_address_normalized}")
                
                token_balance = db.query(TokenBalance).filter(
                    TokenBalance.chain == "insoblok",
                    func.lower(TokenBalance.address) == req.from_address.lower().strip(),
                    func.lower(TokenBalance.token_address) == token_address.lower().strip()
                ).first()
                # if token_address_normalized:
                #     q = q.filter(func.lower(TokenBalance.token_address) == token_address_normalized)
                # else:
                #     q = q.filter(TokenBalance.token_address.is_(None))
                
                # token_balance = q.first()
                # logger.info(f"Case-insensitive query result: {token_balance}")
            
            # Also try without token_address filter (in case it's stored differently)
            if not token_balance:
                logger.info("Trying query without token_address filter...")
                token_balance = db.query(TokenBalance).filter(
                    TokenBalance.chain == "insoblok",
                    func.lower(TokenBalance.address) == req.from_address.lower().strip(),
                    func.lower(TokenBalance.token_address) == token_address.lower().strip()
                ).first()

                logger.info(f"Query by symbol result: {token_balance}")
            
            if token_balance:
                balance = float(token_balance.balance)
                logger.info(f"✓ Found balance record: ID={token_balance.id}, balance={balance:.6f} INSO")
                logger.info(f"  Record address: {repr(token_balance.address)}")
                logger.info(f"  Record token_address: {repr(token_balance.token_address)}")
                logger.info(f"  Record token_symbol: {token_balance.token_symbol}")
            else:
                balance = 0.0
                logger.warning(f"✗ No database balance record found for {req.from_address} on {req.chain}")
                
                # Debug: Show ALL insoblok records
                all_insoblok = db.query(TokenBalance).filter(TokenBalance.chain == "insoblok").all()
                logger.info(f"Total insoblok records in database: {len(all_insoblok)}")
                for b in all_insoblok:
                    logger.info(f"  Record: address={repr(b.address)}, token_address={repr(b.token_address)}, "
                              f"token_symbol={b.token_symbol}, balance={b.balance}, "
                              f"address_lower={b.address.lower() if b.address else None}")
            
            logger.info(f"Final balance: {balance:.6f} INSO (requested: {req.amount:.6f} INSO)")
            logger.info(f"=== End balance check ===")
        else:
            # For other chains, check blockchain balance
            balance_raw = token.functions.balanceOf(from_address_checksum).call()
            balance = float(balance_raw) / (10 ** decimals)
            logger.info(f"Blockchain balance check for {req.from_address} on {req.chain}: {balance:.6f} (requested: {req.amount:.6f})")
        
        if balance < req.amount:
            error_detail = {
                "error": "InsufficientBalance",
                "message": f"Insufficient INSO token balance on {req.chain}",
                "current_balance": f"{balance:.6f}",
                "required_amount": f"{req.amount:.6f}",
                "shortage": f"{req.amount - balance:.6f}",
                "chain": req.chain,
                "token_address": token_address,
                "suggestion": "Please add more INSO tokens to your wallet before attempting to send."
            }
            logger.warning(f"Insufficient balance detected: {error_detail}")
            raise HTTPException(
                status_code=400,
                detail=error_detail
            )
    except HTTPException:
        raise
    except Exception as balance_error:
        logger.error(f"Error checking balance before gas estimation: {str(balance_error)}", exc_info=True)
        # Continue with gas estimation - it will fail with contract error if balance is insufficient
        # But at least we tried to provide a better error message first

    # For insoblok, tokens are database-only, so skip blockchain gas estimation
    # But we still need to get the correct nonce from the blockchain
    if req.chain == "insoblok":
        logger.info("Skipping blockchain gas estimation for insoblok (database-only tokens)")
        # Use default gas values for ERC20 transfer
        gas_limit = 100000  # Standard ERC20 transfer gas limit
        # Get actual nonce from blockchain (nonce is account-specific, not token-specific)
        try:
            nonce = w3.eth.get_transaction_count(w3.to_checksum_address(req.from_address), "pending")
            logger.info(f"Got nonce {nonce} from blockchain for {req.from_address}")
        except Exception as e:
            logger.warning(f"Error getting nonce for insoblok, using 0: {str(e)}")
            nonce = 0
        base_fee = 20000000000  # 20 gwei default
        priority = 1000000000  # 1 gwei default
        max_fee = int(base_fee * 2 + priority)
    else:
        # Build call data for estimation
        data = token.encode_abi("transfer", args=[w3.to_checksum_address(req.to), amount_wei])
        # Nonce
        nonce = w3.eth.get_transaction_count(w3.to_checksum_address(req.from_address), "pending")

        # Suggest EIP-1559 fees
        try:
            latest_block = w3.eth.get_block("latest")
            base_fee = latest_block.get("baseFeePerGas", 0) or 0
        except Exception as e:
            logger.warning(f"Error getting base fee for {req.chain}, using default: {str(e)}")
            base_fee = 0
        
        try:
            priority = w3.eth.max_priority_fee  # node suggestion
        except Exception as e:
            logger.warning(f"Error getting max priority fee for {req.chain}, using default: {str(e)}")
            priority = 1000000000  # 1 gwei default
        
        # Add a cushion to maxFeePerGas
        max_fee = int(base_fee * 2 + priority) if base_fee > 0 else int(priority * 3)

        # Estimate gas
        tx_for_estimate = {
            "from": w3.to_checksum_address(req.from_address),
            "to": w3.to_checksum_address(token_address),
            "value": 0,
            "data": data,
        }
        
        try:
            gas_limit = w3.eth.estimate_gas(tx_for_estimate)
        except (ContractLogicError, ContractCustomError) as e:
            # Transaction would revert - likely insufficient balance or allowance
            error_msg = str(e)
            logger.warning(f"Gas estimation failed for {req.chain} (transaction would revert): {error_msg}")
            logger.warning(f"From: {req.from_address}, To: {req.to}, Amount: {req.amount}, Token: {token_address}")
            
            # Check actual balance and allowance to provide specific error message
            try:
                from_address_checksum = w3.to_checksum_address(req.from_address)
                balance_raw = token.functions.balanceOf(from_address_checksum).call()
                balance = float(balance_raw) / (10 ** decimals)
                
                # Check allowance (for contract-based transfers, check allowance to the contract itself)
                # For direct transfers, allowance might not be needed, but let's check anyway
                try:
                    # Check if there's an allowance set (to any address, or to the contract)
                    allowance_raw = token.functions.allowance(from_address_checksum, from_address_checksum).call()
                    allowance = float(allowance_raw) / (10 ** decimals)
                except:
                    allowance = None
                
                # Determine the specific issue
                if balance < req.amount:
                    user_message = f"Transaction would fail on {req.chain}. Insufficient INSO token balance. You have {balance:.6f} INSO but need {req.amount:.6f} INSO."
                else:
                    # Balance is sufficient, so it's likely an allowance issue
                    user_message = f"Transaction would fail on {req.chain}. Insufficient token allowance. Please approve the INSO token contract (0x724c5ECcB208992747E30ea6BB5E558F8bF770d5) to spend your tokens first."
            except Exception as check_error:
                # If we can't check balance/allowance, provide generic message
                logger.warning(f"Could not check balance/allowance: {str(check_error)}")
                
                # Try to decode the custom error if it's a ContractCustomError
                error_name = None
                if isinstance(e, ContractCustomError):
                    try:
                        # The error selector 0xe450d38c is ERC20InsufficientBalance
                        error_data = str(e)
                        if '0xe450d38c' in error_data or 'e450d38c' in error_data.lower():
                            error_name = "ERC20InsufficientBalance"
                    except:
                        pass
                
                # Provide a user-friendly error message
                user_message = f"Transaction would fail on {req.chain}. "
                if error_name == "ERC20InsufficientBalance":
                    user_message += "Insufficient INSO token balance. Please ensure you have enough tokens in your wallet."
                else:
                    # Default message
                    error_lower = error_msg.lower()
                    if "insufficient" in error_lower and "balance" in error_lower:
                        user_message += "Insufficient INSO token balance. Please ensure you have enough tokens."
                    elif "insufficient" in error_lower and "allowance" in error_lower:
                        user_message += "Insufficient token allowance. Please approve the INSO token contract first."
                    elif "allowance" in error_lower or "approve" in error_lower:
                        user_message += "Token allowance required. Please approve the INSO token contract to spend your tokens."
                    else:
                        user_message += "Please check your INSO token balance and ensure you have approved the token contract if needed."
            
            raise HTTPException(
                status_code=400,
                detail=user_message
            )
        except Exception as e:
            # Other errors during gas estimation
            error_msg = str(e)
            logger.error(f"Error estimating gas: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to estimate gas: {error_msg}"
            )
    
    return {
        "chainId": NETWORK_CONFIGS[req.chain]["chainId"],
        "nonce": nonce,
        "gasLimit": gas_limit,
        "maxFeePerGas":max_fee,
        'baseFeePerGas': base_fee,
        "maxPriorityFeePerGas": int(priority),
        "tokenDecimals": int(decimals),
    }

def doTransferERC20(sender, recipient, amount, chain, pk):
    try:
        w3 = _get_w3(chain)
        token_address = NETWORK_CONFIGS[chain]["token_address"]
        if not token_address:
            raise ValueError(f"No token address configured for chain '{chain}'")
        
        contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=ERC20_ABI)
        sender_checksum = w3.to_checksum_address(sender)
        
        # Get token decimals from contract
        try:
            decimals = contract.functions.decimals().call()
        except Exception:
            decimals = 18  # Default to 18 if decimals() call fails
        
        # Calculate amount in token units
        amount_units = int(amount * (10 ** decimals))
        
        nonce = w3.eth.get_transaction_count(sender_checksum)
        txn = contract.functions.transfer(w3.to_checksum_address(recipient), amount_units).build_transaction({
            "from": sender_checksum,
            "nonce": nonce,
            "gas": 100000,
            "gasPrice": w3.eth.gas_price,
            "chainId": NETWORK_CONFIGS[chain]["chainId"]
        })
        signed_txn = w3.eth.account.sign_transaction(txn, private_key=pk)
        # Web3.py uses rawTransaction (camelCase)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        return tx_hash
    except Exception as e:
        logger.error(f"Error in doTransferERC20: {str(e)}")
        return None

def transferERC20(db: Session, sender, recipient, amount, chain, pk, save=True):
    try:
        # Get token address and info
        token_address = NETWORK_CONFIGS[chain]["token_address"]
        if not token_address:
            raise HTTPException(
                status_code=400,
                detail=f"No token address configured for chain '{chain}'"
            )
        
        w3 = _get_w3(chain)
        contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=ERC20_ABI)
        
        # Get token symbol
        try:
            token_symbol = contract.functions.symbol().call()
        except Exception:
            token_symbol = "TOKEN"  # Default if symbol() call fails
        
        # Transfer tokens
        tx_hash = doTransferERC20(sender, recipient, amount, chain, pk)
        
        if tx_hash is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to send transaction"
            )
        
        # Convert HexBytes to hex string
        tx_hash_str = tx_hash.hex() if hasattr(tx_hash, 'hex') else str(tx_hash)
        if not tx_hash_str.startswith('0x'):
            tx_hash_str = f"0x{tx_hash_str}"
        
        logger.info(f"Transaction hash is {tx_hash_str}")
        
        new_history = TxHistory(
            from_address=sender,
            to_address=recipient,
            token_symbol=token_symbol,
            amount=amount,
            tx_hash=tx_hash_str,
            status="pending",
            chain=chain
        )
        if save:
            db.add(new_history)
            db.commit()
            db.refresh(new_history)
        return new_history
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in transferERC20: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error transferring tokens: {str(e)}"
        )
    
async def watch_block(network_name, config):
    # Connect via WebSocket, NOT HTTP
    db = SessionLocal()
    async with AsyncWeb3(AsyncWeb3.WebSocketProvider(config["wss_url"], websocket_kwargs={'max_size': 10 * 1024 * 1024})) as w3:
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        if await w3.is_connected():
            print("Connect successfully.")
        else:
            print("connection failed.")
            return
    # Subscribe to new blocks
        subscription_id = await w3.eth.subscribe('newHeads')
        print(subscription_id)
        
        print(f"Listening for new blocks in {network_name}")
        log_info(f"Listening for new blocks in {network_name}")
        async for response in w3.socket.process_subscriptions():
            block = response["result"]
            block_number = block['number']
            print(f"New block: {block_number} in {network_name} at {datetime.now()}")
            log_info(f"New block: {block_number} in {network_name} at {datetime.now()}")
            # Get the full block with all transactions
            full_block = await w3.eth.get_block(block_number, full_transactions=True)
            
            # Get monitored addresses for incoming transaction detection
            # Lazy import to avoid circular dependency
            try:
                from services.receiving import process_block_transactions, get_monitored_addresses
                monitored_addresses = get_monitored_addresses(db)
                
                # Process block for incoming transactions to monitored addresses
                if monitored_addresses and full_block.get('transactions'):
                    try:
                        detected_count = process_block_transactions(
                            db=db,
                            block_transactions=full_block['transactions'],
                            chain=network_name,
                            monitored_addresses=monitored_addresses
                        )
                        if detected_count > 0:
                            logger.info(f"Detected {detected_count} incoming transaction(s) in block {block_number}")
                    except Exception as e:
                        logger.error(f"Error processing block {block_number} for incoming transactions: {str(e)}")
            except ImportError as e:
                logger.warning(f"Receiving module not available: {str(e)}")
            
            # Check each transaction in the block for status updates
            for tx in full_block['transactions']:
                tx_hash = tx['hash'].hex()

                # Check if this is a transaction we are waiting for
                tx_record = db.query(TxHistory).filter_by(tx_hash=tx_hash).all()
                if tx_record and len(tx_record) == 1 and tx_record[0].status == "pending":
                    # Get the receipt to get the final status
                    receipt = await w3.eth.get_transaction_receipt(tx_hash)
                    status = "success" if receipt.status == 1 else "failed"

                    # Update the database
                    db.query(TxHistory).filter_by(tx_hash=tx_hash).update(
                        {"status": status}
                    )
                    db.commit()
                    print(f"Updated tx {tx_hash} to status: {status}")
                    
                    # Send notification if transaction succeeded
                    if status == "success":
                        try:
                            notify_transaction_success(tx_record[0], tx_record[0].to_address)
                        except Exception as e:
                            logger.error(f"Error sending notification for tx {tx_hash}: {str(e)}")

def watch_blocks():
    for network_name, config in NETWORK_CONFIGS.items():
        asyncio.create_task(watch_block(network_name, config))

def update_transaction_status():
    succeeded_ids = []
    failed_ids = []
    db = SessionLocal()
    try:
        tx_histories = db.query(TxHistory).filter(TxHistory.status == "pending").all()
        for tx in tx_histories:
            chain = tx.chain
            w3 = _get_w3(chain)
            receipt = w3.eth.get_transaction_receipt(tx.tx_hash)
            print(f"receipt: {receipt}")
            if receipt["status"] == 1:
                succeeded_ids.append(tx.id)
            elif receipt["status"] == 0:
                failed_ids.append(tx.id)
                
            if len(succeeded_ids) > 0:
                query = update(TxHistory).where(TxHistory.id.in_(succeeded_ids)).values(status="success")
                db.execute(query)
                db.commit()
                # Send notifications for successful transactions
                for tx_id in succeeded_ids:
                    tx = db.query(TxHistory).filter(TxHistory.id == tx_id).first()
                    if tx:
                        try:
                            notify_transaction_success(tx, tx.to_address)
                        except Exception as e:
                            logger.error(f"Error sending notification for tx {tx.tx_hash}: {str(e)}")
            if len(failed_ids) > 0:
                query = update(TxHistory).where(TxHistory.id.in_(failed_ids)).values(status="failed")
                db.execute(query)
                db.commit()
        succeeded_ids.clear()
        failed_ids.clear()
        swap_histories = db.query(SwapHistory).filter(SwapHistory.status == "pending").all()
        for tx in swap_histories:
            chain = tx.to_token_network
            w3 = _get_w3(chain)
            receipt = w3.eth.get_transaction_receipt(tx.tx_hash)
            print(f"receipt: {receipt}")
            if receipt["status"] == 1:
                succeeded_ids.append(tx.id)
            elif receipt["status"] == 0:
                failed_ids.append(tx.id)
                
            if len(succeeded_ids) > 0:
                query = update(SwapHistory).where(SwapHistory.id.in_(succeeded_ids)).values(status="success")
                db.execute(query)
                db.commit()
                # Send notifications for successful swaps
                for swap_id in succeeded_ids:
                    swap = db.query(SwapHistory).filter(SwapHistory.id == swap_id).first()
                    if swap:
                        try:
                            notify_swap_success(swap, swap.address)
                        except Exception as e:
                            logger.error(f"Error sending swap notification for tx {swap.tx_hash}: {str(e)}")
            if len(failed_ids) > 0:
                query = update(SwapHistory).where(SwapHistory.id.in_(failed_ids)).values(status="failed")
                db.execute(query)
                db.commit()
    except Exception as e:
        print(str(e))
        