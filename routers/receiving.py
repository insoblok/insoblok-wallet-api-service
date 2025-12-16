from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from services.receiving import check_address_for_incoming, get_monitored_addresses, detect_incoming_transaction
from schemas.receiving import MonitorAddressRequest, CheckAddressRequest, IncomingTransactionResponse
from services.networks.evm import _get_w3
from models import TxHistory
from web3 import Web3
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/monitor")
def add_monitored_address(req: MonitorAddressRequest, db: Session = Depends(get_db)):
    """
    Add an address to monitor for incoming transactions.
    Note: Currently uses existing transaction history. 
    For production, consider adding a dedicated MonitoredAddress table.
    """
    try:
        # Validate address format
        w3 = _get_w3(req.chain if req.chain else "ethereum")
        if not w3.is_address(req.address):
            raise HTTPException(
                status_code=400,
                detail="Invalid address format"
            )
        
        # Address will be automatically monitored if it appears in transaction history
        # For now, we just return success
        # In production, you'd add it to a MonitoredAddress table here
        return {
            "message": "Address will be monitored for incoming transactions",
            "address": Web3.to_checksum_address(req.address),
            "chain": req.chain or "all chains"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding monitored address: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error adding monitored address: {str(e)}"
        )


@router.get("/monitor")
def get_monitored_addresses_list(db: Session = Depends(get_db)):
    """
    Get list of addresses currently being monitored.
    """
    try:
        addresses = get_monitored_addresses(db)
        return {
            "monitored_addresses": addresses,
            "count": len(addresses)
        }
    except Exception as e:
        logger.error(f"Error getting monitored addresses: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting monitored addresses: {str(e)}"
        )


@router.post("/check")
def check_incoming_transactions(req: CheckAddressRequest, db: Session = Depends(get_db)):
    """
    Manually check an address for incoming transactions.
    Useful for initial sync or manual checks.
    """
    try:
        # Validate address
        w3 = _get_w3(req.chain)
        if not w3.is_address(req.address):
            raise HTTPException(
                status_code=400,
                detail="Invalid address format"
            )
        
        address_checksum = Web3.to_checksum_address(req.address)
        
        # Check for incoming transactions
        detected = check_address_for_incoming(
            db=db,
            address=address_checksum,
            chain=req.chain,
            from_block=req.from_block
        )
        
        return {
            "address": address_checksum,
            "chain": req.chain,
            "detected_count": len(detected),
            "transactions": [
                {
                    "tx_hash": tx.tx_hash,
                    "from_address": tx.from_address,
                    "to_address": tx.to_address,
                    "amount": tx.amount,
                    "token_symbol": tx.token_symbol,
                    "status": tx.status,
                    "created_at": tx.created_at.isoformat() if tx.created_at else None
                }
                for tx in detected
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking incoming transactions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error checking incoming transactions: {str(e)}"
        )


@router.get("/incoming/{address}")
def get_incoming_transactions(address: str, chain: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Get all incoming transactions for a specific address.
    """
    try:
        from sqlalchemy import or_
        
        # Query transactions where this address is the recipient
        query = db.query(TxHistory).filter(TxHistory.to_address == address)
        
        if chain:
            query = query.filter(TxHistory.chain == chain)
        
        transactions = query.order_by(TxHistory.created_at.desc()).all()
        
        return {
            "address": address,
            "chain": chain or "all",
            "count": len(transactions),
            "transactions": [
                {
                    "tx_hash": tx.tx_hash,
                    "from_address": tx.from_address,
                    "to_address": tx.to_address,
                    "amount": tx.amount,
                    "token_symbol": tx.token_symbol,
                    "status": tx.status,
                    "chain": tx.chain,
                    "created_at": tx.created_at.isoformat() if tx.created_at else None
                }
                for tx in transactions
            ]
        }
    except Exception as e:
        logger.error(f"Error getting incoming transactions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting incoming transactions: {str(e)}"
        )

