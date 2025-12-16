from sqlalchemy.orm import Session
from sqlalchemy import or_
from models import TokenBalance, TxHistory, SwapHistory
from services.networks import evm as evm_service
from datetime import datetime, timedelta
from datetime import datetime


def get_transaction_status(db: Session, tx_hash: str):
    tx = db.query(TxHistory).filter(TxHistory.tx_hash == tx_hash).first()
    if tx.status == "pending":
        status = evm_service.get_transaction()
    return tx or None

def get_transactions_for_address(address: str, db: Session):
    tx_histories = db.query(TxHistory).filter(or_(TxHistory.from_address == address, TxHistory.to_address == address)).all()
    swap_histories = db.query(SwapHistory).filter(SwapHistory.address == address).all()
    all_histories = list(tx_histories) + list(swap_histories)
    sorted_histories = sorted(all_histories, key=lambda x: x.created_at, reverse=True)
    return sorted_histories


    