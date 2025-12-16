from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services.networks.inso import InSoService
from schemas.evm import BalanceRequest, TransactionRequest
from typing import List

router = APIRouter()

inso_service = InSoService()
@router.post("/balance")
def get_balance(req: BalanceRequest, db: Session = Depends(get_db)):
    return inso_service.get_token_balance(db, req)

@router.post("/send")
def send_tx(req: TransactionRequest, db: Session = Depends(get_db)):
    return inso_service.send_token(db, req)

@router.get("/transaction/{tx_hash}")
def get_transaction(tx_hash: str, chain: str, db: Session = Depends(get_db)):
    return inso_service.get_transaction(db, tx_hash, chain)
