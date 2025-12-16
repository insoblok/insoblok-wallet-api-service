from sqlalchemy import Column, String, Float, DateTime, Integer
from datetime import datetime
from database import Base, engine

class TokenBalance(Base):
    __tablename__ = "token_balances"

    id = Column(Integer, primary_key=True, index=True)
    chain = Column(String, index=True)                        # e.g. "eth", "bsc"
    address = Column(String, index=True)                      # wallet address
    token_address = Column(String, index=True, nullable=True) # contract address or null for native
    token_symbol = Column(String, index=True)
    decimals = Column(Integer, nullable=True)
    balance_raw = Column(String, nullable=True)               # store big integer as string
    balance = Column(Float, default=0.0)                      # human readable decimal
    updated_at = Column(DateTime, default=datetime.utcnow)

class TxHistory(Base):
    __tablename__ = "tx_histories"

    id = Column(Integer, primary_key=True, index=True)
    from_address = Column(String, index=True)
    to_address = Column(String, index=True)
    token_symbol = Column(String)
    amount = Column(Float)
    tx_hash = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, index=True)
    chain = Column(String)
    
class SwapHistory(Base):
    __tablename__ = "swap_histories"
    id = Column(Integer, primary_key=True, index=True)
    address=Column(String, index=True)
    tx_hash = Column(String, unique=True, index=True)
    from_token_network = Column(String, index=True)
    to_token_network = Column(String, index=True)
    from_amount = Column(Float, default=0.0)
    to_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)
    status = Column(String, index=True)
    

Base.metadata.create_all(bind=engine)
