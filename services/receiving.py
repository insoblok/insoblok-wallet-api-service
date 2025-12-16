"""
Receiving module - Detects and processes incoming transactions to monitored addresses.
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from models import TxHistory, TokenBalance
from services.notification import notify_transaction_success
from web3 import Web3
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependency with services.networks.evm
def _get_w3_lazy(chain: str):
    """Lazy import of _get_w3 to avoid circular dependency"""
    from services.networks.evm import _get_w3
    return _get_w3(chain)

def _get_erc20_abi():
    """Lazy import of ERC20_ABI to avoid circular dependency"""
    from services.networks.evm import ERC20_ABI
    return ERC20_ABI


def detect_incoming_transaction(
    db: Session,
    tx_hash: str,
    chain: str,
    from_address: str,
    to_address: str,
    value: int,
    block_number: int,
    token_address: Optional[str] = None
) -> Optional[TxHistory]:
    """
    Detect and record an incoming transaction.
    
    Args:
        db: Database session
        tx_hash: Transaction hash
        chain: Chain name (ethereum, sepolia, etc.)
        from_address: Sender address
        to_address: Recipient address (monitored address)
        value: Transaction value in wei (for native tokens) or token amount
        block_number: Block number
        token_address: Token contract address (None for native token)
    
    Returns:
        TxHistory object if transaction was recorded, None otherwise
    """
    try:
        # Check if transaction already exists
        existing_tx = db.query(TxHistory).filter(TxHistory.tx_hash == tx_hash).first()
        if existing_tx:
            logger.debug(f"Transaction {tx_hash} already exists in database")
            return existing_tx
        
        w3 = _get_w3_lazy(chain)
        
        # Determine token symbol and amount
        if token_address:
            # ERC20 token transfer
            try:
                erc20_abi = _get_erc20_abi()
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(token_address),
                    abi=erc20_abi
                )
                decimals = contract.functions.decimals().call()
                symbol = contract.functions.symbol().call()
                amount = float(value) / (10 ** decimals)
            except Exception as e:
                logger.warning(f"Error getting token info for {token_address}: {str(e)}")
                symbol = "UNKNOWN"
                amount = float(value) / (10 ** 18)  # Default to 18 decimals
        else:
            # Native token (ETH, etc.)
            symbol = "ETH" if chain == "ethereum" else "ETH"  # Adjust based on chain
            amount = float(Web3.from_wei(value, "ether"))
        
        # Create transaction record
        new_tx = TxHistory(
            from_address=from_address,
            to_address=to_address,
            token_symbol=symbol,
            amount=amount,
            tx_hash=tx_hash,
            status="success",  # If we're detecting it, it's already confirmed
            chain=chain
        )
        
        db.add(new_tx)
        db.commit()
        db.refresh(new_tx)
        
        logger.info(f"Recorded incoming transaction {tx_hash}: {amount} {symbol} to {to_address}")
        
        # Send notification to recipient
        try:
            notify_transaction_success(new_tx, to_address)
        except Exception as e:
            logger.error(f"Error sending notification for incoming tx {tx_hash}: {str(e)}")
        
        return new_tx
        
    except Exception as e:
        logger.error(f"Error detecting incoming transaction {tx_hash}: {str(e)}")
        db.rollback()
        return None


def process_block_transactions(db: Session, block_transactions: List[Dict], chain: str, monitored_addresses: List[str]) -> int:
    """
    Process transactions in a block and detect incoming transactions to monitored addresses.
    
    Args:
        db: Database session
        block_transactions: List of transaction dictionaries from the block
        chain: Chain name
        monitored_addresses: List of addresses to monitor for incoming transactions
    
    Returns:
        Number of incoming transactions detected
    """
    if not monitored_addresses:
        return 0
    
    detected_count = 0
    w3 = _get_w3_lazy(chain)
    
    # Normalize monitored addresses to checksum format
    monitored_checksum = [Web3.to_checksum_address(addr) for addr in monitored_addresses]
    
    for tx in block_transactions:
        try:
            tx_hash = tx['hash'].hex() if hasattr(tx['hash'], 'hex') else tx['hash']
            to_address = tx.get('to')
            from_address = tx.get('from')
            value = tx.get('value', 0)
            
            # Check if this is an incoming transaction to a monitored address
            if to_address and Web3.to_checksum_address(to_address) in monitored_checksum:
                # Native token transfer
                if value > 0:
                    detect_incoming_transaction(
                        db=db,
                        tx_hash=tx_hash,
                        chain=chain,
                        from_address=from_address,
                        to_address=to_address,
                        value=value,
                        block_number=tx.get('blockNumber', 0),
                        token_address=None
                    )
                    detected_count += 1
                
                # Check for ERC20 token transfers in transaction logs
                if tx.get('logs'):
                    for log in tx['logs']:
                        # ERC20 Transfer event signature: Transfer(address,address,uint256)
                        # topics[0] = event signature
                        # topics[1] = from address (indexed)
                        # topics[2] = to address (indexed)
                        # data = amount (uint256)
                        if len(log.get('topics', [])) == 3 and log.get('topics', [])[0].hex() == '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                            try:
                                # Extract sender from topics[1] (actual token sender, not transaction sender)
                                sender = '0x' + log['topics'][1].hex()[-40:] if hasattr(log['topics'][1], 'hex') else log['topics'][1][-20:].hex()
                                sender_checksum = Web3.to_checksum_address(sender)
                                
                                # Extract recipient from topics[2]
                                recipient = '0x' + log['topics'][2].hex()[-40:] if hasattr(log['topics'][2], 'hex') else log['topics'][2][-20:].hex()
                                recipient_checksum = Web3.to_checksum_address(recipient)
                                
                                if recipient_checksum in monitored_checksum:
                                    token_address = log.get('address')
                                    # Extract amount from data
                                    amount_hex = log.get('data', '0x0')
                                    amount = int(amount_hex, 16) if amount_hex != '0x0' else 0
                                    
                                    if amount > 0:
                                        detect_incoming_transaction(
                                            db=db,
                                            tx_hash=tx_hash,
                                            chain=chain,
                                            from_address=sender_checksum,  # Use token sender from event, not transaction sender
                                            to_address=recipient_checksum,
                                            value=amount,
                                            block_number=tx.get('blockNumber', 0),
                                            token_address=token_address
                                        )
                                        detected_count += 1
                            except Exception as e:
                                logger.warning(f"Error processing ERC20 transfer log: {str(e)}")
                                continue
                                
        except Exception as e:
            logger.error(f"Error processing transaction in block: {str(e)}")
            continue
    
    return detected_count


def get_monitored_addresses(db: Session) -> List[str]:
    """
    Get list of addresses that should be monitored for incoming transactions.
    This can be extended to use a dedicated table for monitored addresses.
    For now, we'll use addresses from TxHistory where this address is the recipient.
    
    Args:
        db: Database session
    
    Returns:
        List of unique addresses to monitor
    """
    # Get all unique recipient addresses from transaction history
    # In a production system, you might want a dedicated MonitoredAddress table
    addresses = db.query(TxHistory.to_address).distinct().all()
    return [addr[0] for addr in addresses if addr[0]]


def check_address_for_incoming(db: Session, address: str, chain: str, from_block: Optional[int] = None) -> List[TxHistory]:
    """
    Check a specific address for incoming transactions.
    Useful for manual checks or initial sync.
    
    Args:
        db: Database session
        address: Address to check
        chain: Chain name
        from_block: Block number to start from (None = latest)
    
    Returns:
        List of detected incoming transactions
    """
    try:
        w3 = _get_w3_lazy(chain)
        address_checksum = Web3.to_checksum_address(address)
        
        if from_block is None:
            from_block = w3.eth.block_number - 100  # Check last 100 blocks
        
        detected = []
        
        # Get transactions from the address (sent transactions)
        # Note: This is a simplified check. For production, you'd want to use event logs
        for block_num in range(from_block, w3.eth.block_number + 1):
            try:
                block = w3.eth.get_block(block_num, full_transactions=True)
                for tx in block.get('transactions', []):
                    if tx.get('to') and Web3.to_checksum_address(tx['to']) == address_checksum:
                        # Native token received
                        if tx.get('value', 0) > 0:
                            incoming_tx = detect_incoming_transaction(
                                db=db,
                                tx_hash=tx['hash'].hex(),
                                chain=chain,
                                from_address=tx.get('from'),
                                to_address=address_checksum,
                                value=tx.get('value', 0),
                                block_number=block_num,
                                token_address=None
                            )
                            if incoming_tx:
                                detected.append(incoming_tx)
            except Exception as e:
                logger.warning(f"Error checking block {block_num}: {str(e)}")
                continue
        
        return detected
        
    except Exception as e:
        logger.error(f"Error checking address {address} for incoming transactions: {str(e)}")
        return []

