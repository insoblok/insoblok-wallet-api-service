from fastapi import APIRouter, Depends
from database import get_db
from services.common import get_transaction_status, get_transactions_for_address
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/transaction/{tx_hash}")
def get_transaction_status(tx_hash: str, db: Session = Depends(get_db)):
    return get_transaction_status(db, tx_hash)

@router.get("/transactions/{address}")
def get_transactions(address: str, db: Session = Depends(get_db)):
    return get_transactions_for_address(address, db)