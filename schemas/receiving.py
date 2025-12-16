from pydantic import BaseModel
from typing import Optional, List

class MonitorAddressRequest(BaseModel):
    address: str  # Address to monitor for incoming transactions
    chain: Optional[str] = ""  # Specific chain, or "" for all chains

class CheckAddressRequest(BaseModel):
    address: str  # Address to check
    chain: str  # Chain name
    from_block: Optional[int] = None  # Block number to start from (optional)

class IncomingTransactionResponse(BaseModel):
    tx_hash: str
    from_address: str
    to_address: str
    amount: float
    token_symbol: str
    chain: str
    block_number: int
    status: str

