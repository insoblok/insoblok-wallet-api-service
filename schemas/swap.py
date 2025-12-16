from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class XP2INSORequest(BaseModel):
    from_amount: float
    to_amount: float
    to_address: str
    
class XP2INSOResponse(BaseModel):
    tx_hash: str
    amount: float
    swap_id: int


# New Swap API Schemas
class SwapQuoteRequest(BaseModel):
    from_token: str
    to_token: str
    amount: float


class SwapQuoteResponse(BaseModel):
    from_token: str
    to_token: str
    from_amount: float
    to_amount: float
    rate: float
    slippage: float
    fee: float
    min_received: float


class SwapExecuteRequest(BaseModel):
    from_token: str
    to_token: str
    from_amount: float
    to_amount: float
    from_address: str
    to_address: str
    chain: str
    slippage_tolerance: Optional[float] = 0.5


class SwapExecuteResponse(BaseModel):
    tx_hash: str
    status: str
    from_token: str
    to_token: str
    from_amount: float
    to_amount: float
    chain: str
    timestamp: str


class SwapStatusResponse(BaseModel):
    tx_hash: str
    status: str
    from_token: str
    to_token: str
    from_amount: float
    to_amount: float
    actual_to_amount: Optional[float] = None
    chain: str
    block_number: Optional[int] = None
    confirmations: Optional[int] = None
    timestamp: str
    completed_at: Optional[str] = None


class SwapHistoryItem(BaseModel):
    tx_hash: str
    status: str
    from_token: str
    to_token: str
    from_amount: float
    to_amount: float
    chain: str
    timestamp: str


class SwapHistoryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    swaps: List[SwapHistoryItem]


# P2P Payment Schemas
class P2PPaymentRequest(BaseModel):
    """Request for P2P payment - same as TransactionRequest but specifically for P2P"""
    chain: str
    signed_raw_tx: str  # hex string of signed transaction
    from_address: str
    to_address: str
    token_symbol: str
    amount: float


class P2PPaymentResponse(BaseModel):
    """Response for P2P payment"""
    tx_hash: str
    status: str
    from_address: str
    to_address: str
    amount: float
    token_symbol: str
    chain: str
    timestamp: str
    
