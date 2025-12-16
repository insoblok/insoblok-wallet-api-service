from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from fastapi import HTTPException
from typing import Optional
from schemas.swap import (
    XP2INSORequest, XP2INSOResponse,
    SwapQuoteRequest, SwapQuoteResponse,
    SwapExecuteRequest, SwapExecuteResponse,
    SwapStatusResponse, SwapHistoryResponse, SwapHistoryItem,
    P2PPaymentRequest, P2PPaymentResponse
)
from models import SwapHistory, TokenBalance
from services.networks import evm as evm_service
from services.networks.evm import _get_w3, NETWORK_CONFIGS, ERC20_ABI
from web3 import Web3
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# Token configuration - maps token symbols to chain and token addresses
# Supports both mainnet and testnet tokens
TOKEN_CONFIG = {
    # Ethereum Mainnet Tokens
    "ETH": {
        "ethereum": {"token_address": None, "decimals": 18},
        "sepolia": {"token_address": None, "decimals": 18},  # Native ETH on Sepolia
    },
    "USDT": {
        "ethereum": {"token_address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
        "sepolia": {"token_address": None, "decimals": 6},  # No official USDT on Sepolia, use test tokens
    },
    # Sepolia Testnet Tokens
    "LINK": {
        "sepolia": {"token_address": "0x779877A7B0D9E8603169DdbD7836e478b4624789", "decimals": 18},
    },
    "DAI": {
        "sepolia": {"token_address": "0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357", "decimals": 18},
    },
    "WETH": {
        "sepolia": {"token_address": "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14", "decimals": 18},
    },
    # INSO Token (on Sepolia/insoblok)
    "INSO": {
        "insoblok": {"token_address": "0x724c5ECcB208992747E30ea6BB5E558F8bF770d5", "decimals": 18},
        "sepolia": {"token_address": "0x724c5ECcB208992747E30ea6BB5E558F8bF770d5", "decimals": 18},  # Same address on Sepolia
    },
    # Other tokens
    "XRP": {
        "xrp": {"token_address": None, "decimals": 6},
    },
    "XP": {
        "internal": {"token_address": None, "decimals": 0},  # Internal token
    },
}

# Default swap rates (can be replaced with DEX aggregator integration)
# Format: (from_token, to_token): rate
# Supports cross-chain swaps between Ethereum mainnet and Sepolia testnet
DEFAULT_SWAP_RATES = {
    # Ethereum Mainnet <-> INSO (Sepolia)
    ("USDT", "INSO"): 100.0,  # 1 USDT = 100 INSO
    ("INSO", "USDT"): 0.01,   # 1 INSO = 0.01 USDT
    ("ETH", "INSO"): 3000.0,  # 1 ETH = 3000 INSO
    ("INSO", "ETH"): 0.000333,  # 1 INSO = 0.000333 ETH
    # Sepolia Testnet <-> INSO
    ("LINK", "INSO"): 15.0,   # 1 LINK = 15 INSO
    ("INSO", "LINK"): 0.0667,  # 1 INSO = 0.0667 LINK
    ("DAI", "INSO"): 100.0,   # 1 DAI = 100 INSO (same as USDT)
    ("INSO", "DAI"): 0.01,    # 1 INSO = 0.01 DAI
    ("WETH", "INSO"): 3000.0, # 1 WETH = 3000 INSO (same as ETH)
    ("INSO", "WETH"): 0.000333, # 1 INSO = 0.000333 WETH
    # Cross-chain Ethereum <-> Sepolia
    ("ETH", "WETH"): 1.0,     # 1 ETH = 1 WETH (cross-chain)
    ("WETH", "ETH"): 1.0,     # 1 WETH = 1 ETH (cross-chain)
    ("USDT", "DAI"): 1.0,     # 1 USDT = 1 DAI (cross-chain, both stablecoins)
    ("DAI", "USDT"): 1.0,     # 1 DAI = 1 USDT (cross-chain)
    # Other
    ("XRP", "INSO"): 0.5,     # 1 XRP = 0.5 INSO
    ("INSO", "XRP"): 2.0,     # 1 INSO = 2 XRP
}

# Swap fee percentage
SWAP_FEE_PERCENTAGE = 0.1  # 0.1%
DEFAULT_SLIPPAGE = 0.5  # 0.5%


def get_token_info(token: str, chain: str) -> Optional[dict]:
    """
    Get token information for a specific token on a specific chain.
    Returns None if token is not available on the chain.
    """
    token_configs = TOKEN_CONFIG.get(token, {})
    return token_configs.get(chain)


def is_token_available_on_chain(token: str, chain: str) -> bool:
    """
    Check if a token is available on a specific chain.
    """
    return get_token_info(token, chain) is not None


def get_swap_rate(from_token: str, to_token: str) -> float:
    """
    Get swap rate between two tokens.
    In production, this should integrate with DEX aggregators (1inch, 0x, etc.)
    """
    # Check direct rate
    if (from_token, to_token) in DEFAULT_SWAP_RATES:
        return DEFAULT_SWAP_RATES[(from_token, to_token)]
    
    # Check reverse rate
    if (to_token, from_token) in DEFAULT_SWAP_RATES:
        return 1.0 / DEFAULT_SWAP_RATES[(to_token, from_token)]
    
    # Default to 1:1 if no rate found
    logger.warning(f"No swap rate found for {from_token} -> {to_token}, using 1:1")
    return 1.0


def get_inso_from_xp(req: XP2INSORequest, db: Session) -> bool:
    """
    Increase INSO token balance for a user's wallet address in the database.
    
    This function directly updates the TokenBalance record in the database,
    increasing the balance by the specified amount. No blockchain transaction is performed.
    
    Args:
        req: XP2INSORequest containing:
            - from_amount: XP amount (not used, kept for compatibility)
            - to_amount: INSO amount to add to balance
            - to_address: Recipient wallet address
        db: Database session
        
    Returns:
        bool: True if the balance was successfully increased, False otherwise
    """
    try:
        # Validate request
        if req.to_amount <= 0:
            logger.error(f"Invalid amount: {req.to_amount}. Amount must be greater than 0")
            return False
        
        if not req.to_address:
            logger.error("to_address is required")
            return False
        
        # Get INSO token configuration
        inso_config = get_token_info("INSO", "insoblok")
        if not inso_config:
            logger.error("INSO token configuration not found for insoblok chain")
            return False
        
        token_address = inso_config.get("token_address")
        decimals = inso_config.get("decimals", 18)
        
        if not token_address:
            logger.error("INSO token address not configured")
            return False
        
        # Find existing TokenBalance record or create new one
        # Normalize address for consistent storage (use checksum format for consistency)
        to_address_normalized = Web3.to_checksum_address(req.to_address) if req.to_address else req.to_address
        
        # Use case-insensitive matching to find existing record
        token_balance = db.query(TokenBalance).filter(
            TokenBalance.chain == "insoblok",
            func.lower(TokenBalance.address) == req.to_address.lower().strip(),
            func.lower(TokenBalance.token_address) == token_address.lower().strip()
        ).first()
        
        now = datetime.utcnow()
        
        if token_balance:
            # Update existing balance - increase by to_amount

            logger.info(f"Updating existing INSO balance for {token_balance.balance}")
            logger.info(f"Updating existing INSO ID for {token_balance.id}")
            
            old_balance = token_balance.balance
            token_balance.balance = token_balance.balance + req.to_amount
            # Ensure address is normalized
            token_balance.address = to_address_normalized
            
            # Update balance_raw (convert to raw units)
            new_balance_raw = int(token_balance.balance * (10 ** decimals))
            token_balance.balance_raw = str(new_balance_raw)
            token_balance.updated_at = now
            
            logger.info(f"Increased INSO balance for {req.to_address}: {old_balance} -> {token_balance.balance} (+{req.to_amount})")
        else:
            # Create new TokenBalance record
            balance_raw = int(req.to_amount * (10 ** decimals))
            token_balance = TokenBalance(
                chain="insoblok",
                address=to_address_normalized,  # Use normalized address for consistency
                token_address=token_address,
                token_symbol="INSO",
                decimals=decimals,
                balance_raw=str(balance_raw),
                balance=req.to_amount,
                updated_at=now
            )
            db.add(token_balance)
            logger.info(f"Created new INSO balance record for {req.to_address}: {req.to_amount} INSO")
        
        db.commit()
        db.refresh(token_balance)
        
        logger.info(f"Successfully increased INSO balance by {req.to_amount} for address {req.to_address}. New balance: {token_balance.balance}")
        return True
        
    except Exception as e:
        logger.error(f"Error increasing INSO balance: {str(e)}", exc_info=True)
        db.rollback()
        return False 


def get_swap_quote(req: SwapQuoteRequest, db: Session) -> SwapQuoteResponse:
    """
    Get swap quote with rate, fees, and estimated output amount.
    """
    try:
        # Validate tokens
        if req.from_token not in TOKEN_CONFIG:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported from_token: {req.from_token}. Supported tokens: {list(TOKEN_CONFIG.keys())}"
            )
        
        if req.to_token not in TOKEN_CONFIG:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported to_token: {req.to_token}. Supported tokens: {list(TOKEN_CONFIG.keys())}"
            )
        
        if req.from_token == req.to_token:
            raise HTTPException(
                status_code=400,
                detail="from_token and to_token cannot be the same"
            )
        
        if req.amount <= 0:
            raise HTTPException(
                status_code=422,
                detail="Invalid amount. Amount must be greater than 0"
            )
        
        # Get swap rate
        rate = get_swap_rate(req.from_token, req.to_token)
        
        # Calculate output amount
        to_amount = req.amount * rate
        
        # Calculate fee
        fee = req.amount * (SWAP_FEE_PERCENTAGE / 100)
        
        # Calculate amount after fee
        amount_after_fee = req.amount - fee
        to_amount_after_fee = amount_after_fee * rate
        
        # Calculate minimum received (with slippage)
        slippage = DEFAULT_SLIPPAGE
        min_received = to_amount_after_fee * (1 - slippage / 100)
        
        return SwapQuoteResponse(
            from_token=req.from_token,
            to_token=req.to_token,
            from_amount=req.amount,
            to_amount=to_amount_after_fee,
            rate=rate,
            slippage=slippage,
            fee=fee,
            min_received=min_received
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting swap quote: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting swap quote: {str(e)}"
        )


def execute_swap(req: SwapExecuteRequest, db: Session) -> SwapExecuteResponse:
    """
    Execute a token swap transaction.
    """
    try:
        # Validate tokens
        if req.from_token not in TOKEN_CONFIG:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported from_token: {req.from_token}"
            )
        
        if req.to_token not in TOKEN_CONFIG:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported to_token: {req.to_token}"
            )
        
        if req.from_token == req.to_token:
            raise HTTPException(
                status_code=400,
                detail="from_token and to_token cannot be the same"
            )
        
        if req.from_amount <= 0 or req.to_amount <= 0:
            raise HTTPException(
                status_code=422,
                detail="Amounts must be greater than 0"
            )
        
        # Validate chain
        if req.chain not in NETWORK_CONFIGS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported chain: {req.chain}"
            )
        
        # Get token configurations
        from_token_configs = TOKEN_CONFIG.get(req.from_token, {})
        to_token_configs = TOKEN_CONFIG.get(req.to_token, {})
        
        # Determine the chain for from_token (use req.chain if token supports it, otherwise use first available)
        from_chain = None
        if req.chain in from_token_configs:
            from_chain = req.chain
        elif len(from_token_configs) > 0:
            from_chain = list(from_token_configs.keys())[0]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Token {req.from_token} not available on chain {req.chain}"
            )
        
        # Determine the chain for to_token
        to_chain = None
        if req.chain in to_token_configs:
            to_chain = req.chain
        elif len(to_token_configs) > 0:
            # For cross-chain swaps, use the token's native chain
            to_chain = list(to_token_configs.keys())[0]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Token {req.to_token} not available on chain {req.chain}"
            )
        
        # Check if this is a cross-chain swap
        is_cross_chain = from_chain != to_chain
        
        # Validate addresses on the source chain
        w3_from = _get_w3(from_chain)
        if not w3_from.is_address(req.from_address) or not w3_from.is_address(req.to_address):
            raise HTTPException(
                status_code=400,
                detail="Invalid address format"
            )
        
        # Check balance on the source chain (for ERC20 tokens)
        from_token_info = from_token_configs[from_chain]
        if from_token_info.get("token_address"):
            # Check ERC20 balance
            contract = w3_from.eth.contract(
                address=Web3.to_checksum_address(from_token_info["token_address"]),
                abi=ERC20_ABI
            )
            balance_raw = contract.functions.balanceOf(
                Web3.to_checksum_address(req.from_address)
            ).call()
            balance = float(balance_raw) / (10 ** from_token_info["decimals"])
            
            if balance < req.from_amount:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient balance. Available: {balance}, Required: {req.from_amount}"
                )
        elif from_token_info.get("token_address") is None:
            # Native token (ETH) - check native balance
            balance_wei = w3_from.eth.get_balance(Web3.to_checksum_address(req.from_address))
            balance = float(w3_from.from_wei(balance_wei, 'ether'))
            
            if balance < req.from_amount:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient balance. Available: {balance}, Required: {req.from_amount}"
                )
        
        # Verify quote (check slippage)
        rate = get_swap_rate(req.from_token, req.to_token)
        expected_to_amount = req.from_amount * rate
        fee = req.from_amount * (SWAP_FEE_PERCENTAGE / 100)
        expected_after_fee = (req.from_amount - fee) * rate
        
        slippage = abs((expected_after_fee - req.to_amount) / expected_after_fee * 100) if expected_after_fee > 0 else 0
        
        if slippage > req.slippage_tolerance:
            raise HTTPException(
                status_code=422,
                detail=f"Slippage tolerance exceeded. Current rate: {expected_after_fee:.2f}, Expected: {req.to_amount:.2f}, Slippage: {slippage:.2f}%"
            )
        
        # Execute swap based on token types
        tx_hash = None
        to_token_info = to_token_configs[to_chain]
        
        # Handle swaps to INSO (server-side transfer on Sepolia/insoblok)
        if req.to_token == "INSO":
            # Server-side transfer (similar to XP to INSO)
            # This works for both same-chain and cross-chain swaps to INSO
            tx_hash = evm_service.doTransferERC20(
                os.getenv("ADDRESS"),
                req.to_address,
                req.to_amount,
                to_chain,  # Use to_chain (insoblok/sepolia)
                os.getenv("PRIVATE_KEY")
            )
        elif is_cross_chain:
            # Cross-chain swap between Ethereum and Sepolia
            # For now, we support cross-chain swaps to INSO only
            # In production, you would integrate with a bridge service
            if req.to_token == "INSO":
                # Already handled above
                pass
            else:
                # For other cross-chain swaps, you would:
                # 1. Integrate with bridge protocol (like Across, Hop, etc.)
                # 2. Or use a custodial bridge service
                # For now, raise an error for unsupported cross-chain swaps
                raise HTTPException(
                    status_code=400,
                    detail=f"Cross-chain swap from {req.from_token} ({from_chain}) to {req.to_token} ({to_chain}) not yet implemented. Currently supports swaps to INSO only."
                )
        else:
            # Same-chain swap (not to INSO)
            # For same-chain swaps, you would:
            # 1. Integrate with DEX aggregator (1inch, 0x, etc.)
            # 2. Build swap transaction
            # 3. Sign and broadcast
            # For now, raise an error for unsupported swaps
            raise HTTPException(
                status_code=400,
                detail=f"Swap from {req.from_token} to {req.to_token} on {req.chain} not yet implemented. Currently supports swaps to INSO and cross-chain swaps to INSO."
            )
        
        if tx_hash is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to execute swap transaction"
            )
        
        # Convert tx_hash to string
        tx_hash_str = tx_hash.hex() if hasattr(tx_hash, 'hex') else str(tx_hash)
        if not tx_hash_str.startswith('0x'):
            tx_hash_str = f"0x{tx_hash_str}"
        
        # Save swap history with chain information
        # Store chain info in token_network field as "token:chain" format for cross-chain swaps
        from_token_network = f"{req.from_token.lower()}:{from_chain}" if is_cross_chain else req.from_token.lower()
        to_token_network = f"{req.to_token.lower()}:{to_chain}" if is_cross_chain else req.to_token.lower()
        
        swap_history = SwapHistory(
            tx_hash=tx_hash_str,
            address=req.to_address,
            from_token_network=from_token_network,
            to_token_network=to_token_network,
            from_amount=req.from_amount,
            to_amount=req.to_amount,
            status="pending"
        )
        db.add(swap_history)
        db.commit()
        db.refresh(swap_history)
        
        # Return chain of the destination token for cross-chain swaps
        return_chain = to_chain if is_cross_chain else req.chain
        
        return SwapExecuteResponse(
            tx_hash=tx_hash_str,
            status="pending",
            from_token=req.from_token,
            to_token=req.to_token,
            from_amount=req.from_amount,
            to_amount=req.to_amount,
            chain=return_chain,  # Return destination chain for cross-chain swaps
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing swap: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error executing swap: {str(e)}"
        )


def get_swap_status(tx_hash: str, db: Session) -> SwapStatusResponse:
    """
    Get the status of a swap transaction.
    """
    try:
        # Find swap in database
        swap = db.query(SwapHistory).filter(SwapHistory.tx_hash == tx_hash).first()
        
        if not swap:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found"
            )
        
        # Get transaction details from blockchain if pending
        block_number = None
        confirmations = None
        actual_to_amount = None
        completed_at = None
        
        if swap.status == "pending":
            # Try to get transaction receipt
            try:
                # Parse chain from token network (format: "token:chain" or "token")
                to_token_network = swap.to_token_network.lower()
                if ":" in to_token_network:
                    # Cross-chain swap format: "token:chain"
                    _, chain = to_token_network.split(":", 1)
                else:
                    # Same-chain swap: extract chain from TOKEN_CONFIG
                    token_symbol = to_token_network.upper()
                    token_configs = TOKEN_CONFIG.get(token_symbol, {})
                    if token_configs:
                        chain = list(token_configs.keys())[0]
                    else:
                        chain = "ethereum"  # Default fallback
                
                if chain in NETWORK_CONFIGS:
                    w3 = _get_w3(chain)
                    receipt = w3.eth.get_transaction_receipt(tx_hash)
                    
                    if receipt:
                        block_number = receipt.blockNumber
                        current_block = w3.eth.block_number
                        confirmations = max(0, current_block - block_number)
                        
                        # Update status based on receipt
                        if receipt.status == 1:
                            swap.status = "success"
                            actual_to_amount = swap.to_amount  # Could calculate from logs
                            completed_at = datetime.utcnow().isoformat() + "Z"
                        else:
                            swap.status = "failed"
                            completed_at = datetime.utcnow().isoformat() + "Z"
                        
                        db.commit()
            except Exception as e:
                logger.warning(f"Could not fetch transaction receipt: {str(e)}")
        
        if swap.status == "success":
            actual_to_amount = swap.to_amount
            completed_at = swap.created_at.isoformat() + "Z" if swap.created_at else None
        
        # Parse token and chain from token_network
        to_token_network = swap.to_token_network.lower()
        if ":" in to_token_network:
            to_token, chain = to_token_network.split(":", 1)
        else:
            to_token = to_token_network
            token_configs = TOKEN_CONFIG.get(to_token.upper(), {})
            chain = list(token_configs.keys())[0] if token_configs else "ethereum"
        
        from_token_network = swap.from_token_network.lower()
        if ":" in from_token_network:
            from_token, _ = from_token_network.split(":", 1)
        else:
            from_token = from_token_network
        
        return SwapStatusResponse(
            tx_hash=swap.tx_hash,
            status=swap.status,
            from_token=from_token.upper(),
            to_token=to_token.upper(),
            from_amount=swap.from_amount,
            to_amount=swap.to_amount,
            actual_to_amount=actual_to_amount,
            chain=chain,
            block_number=block_number,
            confirmations=confirmations,
            timestamp=swap.created_at.isoformat() + "Z" if swap.created_at else datetime.utcnow().isoformat() + "Z",
            completed_at=completed_at
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting swap status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting swap status: {str(e)}"
        )


def get_swap_history(address: str, chain: Optional[str] = None, limit: int = 50, offset: int = 0, db: Session = None) -> SwapHistoryResponse:
    """
    Get swap transaction history for a user.
    """
    try:
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 50
        if offset < 0:
            offset = 0
        
        # Build query
        query = db.query(SwapHistory).filter(SwapHistory.address == address)
        
        # Filter by chain if provided
        if chain:
            # Filter swaps where to_token_network matches chain
            query = query.filter(SwapHistory.to_token_network == chain.lower())
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        swaps = query.order_by(SwapHistory.created_at.desc()).offset(offset).limit(limit).all()
        
        swap_items = []
        for swap in swaps:
            # Parse token and chain from token_network
            to_token_network = swap.to_token_network.lower()
            if ":" in to_token_network:
                to_token, chain = to_token_network.split(":", 1)
            else:
                to_token = to_token_network
                token_configs = TOKEN_CONFIG.get(to_token.upper(), {})
                chain = list(token_configs.keys())[0] if token_configs else "ethereum"
            
            from_token_network = swap.from_token_network.lower()
            if ":" in from_token_network:
                from_token, _ = from_token_network.split(":", 1)
            else:
                from_token = from_token_network
            
            swap_items.append(
                SwapHistoryItem(
                    tx_hash=swap.tx_hash,
                    status=swap.status,
                    from_token=from_token.upper(),
                    to_token=to_token.upper(),
                    from_amount=swap.from_amount,
                    to_amount=swap.to_amount,
                    chain=chain,
                    timestamp=swap.created_at.isoformat() + "Z" if swap.created_at else datetime.utcnow().isoformat() + "Z"
                )
            )
        
        return SwapHistoryResponse(
            total=total,
            limit=limit,
            offset=offset,
            swaps=swap_items
        )
    
    except Exception as e:
        logger.error(f"Error getting swap history: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting swap history: {str(e)}"
        )
