from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from services.networks import evm as evm_service
from schemas.evm import BalanceRequest, TransactionRequest, QuoteRequest, TransferRequest, PublicKeyToAddressRequest
from dotenv import load_dotenv
import os

load_dotenv()


router = APIRouter()

@router.post("/balance")
def get_balance(req: BalanceRequest, db: Session = Depends(get_db)):
    """
    Get balance for an address on a specific chain or all chains.
    
    Request body (JSON):
    {
        "chain": "ethereum" | "sepolia" | "insoblok" | "" (optional, defaults to "" for all chains),
        "address": "0x..." (required),
        "token_symbol": "string" (optional),
        "decimals": 18 (optional)
    }
    
    Example:
    {
        "chain": "ethereum",
        "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb5"
    }
    """
    print("req:");
    print(req.model_dump_json());

    # Address validation is handled by Pydantic validators in schemas/evm.py
    # This ensures consistent validation and better error messages via the validation exception handler
    return evm_service.get_balance(db, req)

@router.post("/send")
def send_tx(req: TransactionRequest, db: Session = Depends(get_db)):
    return evm_service.send_transaction(db, req)

@router.get("/transaction/{chain}/{tx_hash}")
def get_transaction(tx_hash: str, chain: str, db: Session = Depends(get_db)):
    return evm_service.get_transaction(db, tx_hash, chain)

@router.post("/transaction/get-quote")
def get_quote(req: QuoteRequest, db: Session = Depends(get_db)):
    return evm_service.get_quote(db, req)

""" transfer token from a server to requested address

Returns:
    TxHistory: transaction history object
"""
@router.post("/transaction/transfer")
def transfer(req: TransferRequest, db: Session=Depends(get_db)):
    return evm_service.transferERC20(db, req.sender or os.getenv("ADDRESS"), req.recipient, req.amount, req.chain, os.getenv("PRIVATE_KEY"))

@router.post("/public-key-to-address")
def public_key_to_address(req: PublicKeyToAddressRequest):
    """Convert a public key to an Ethereum address"""
    address = evm_service.public_key_to_address(req.public_key)
    return {"address": address}