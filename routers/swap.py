from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from services import swap as swap_service
from schemas.swap import (
    XP2INSORequest, XP2INSOResponse,
    SwapQuoteRequest, SwapQuoteResponse,
    SwapExecuteRequest, SwapExecuteResponse,
    SwapStatusResponse, SwapHistoryResponse
)
from typing import Optional

router = APIRouter()


@router.post("/get-inso-from-xp")
def get_inso_from_xp(req: XP2INSORequest, db: Session = Depends(get_db)):
    """
    Add INSO token balance to a user's wallet address.
    
    This endpoint transfers INSO tokens from the server wallet to the specified address.
    Returns a boolean: True if successful, False otherwise.
    """
    return swap_service.get_inso_from_xp(req, db)


@router.post("/quote", response_model=SwapQuoteResponse)
def get_swap_quote(req: SwapQuoteRequest, db: Session = Depends(get_db)):
    """
    Get swap quote/rate for a token swap.
    
    Returns exchange rate, estimated output amount, fees, and slippage information.
    """
    return swap_service.get_swap_quote(req, db)


@router.post("/execute", response_model=SwapExecuteResponse)
def execute_swap(req: SwapExecuteRequest, db: Session = Depends(get_db)):
    """
    Execute a token swap transaction.
    
    Validates balance, checks slippage tolerance, and executes the swap.
    Returns transaction hash and status.
    """
    return swap_service.execute_swap(req, db)


@router.get("/status/{tx_hash}", response_model=SwapStatusResponse)
def get_swap_status(tx_hash: str, db: Session = Depends(get_db)):
    """
    Get the status of a swap transaction.
    
    Returns current status, confirmations, and actual received amount if completed.
    """
    return swap_service.get_swap_status(tx_hash, db)


@router.get("/history", response_model=SwapHistoryResponse)
def get_swap_history(
    address: str = Query(..., description="User's wallet address"),
    chain: Optional[str] = Query(None, description="Filter by chain (optional)"),
    limit: int = Query(50, ge=1, le=100, description="Number of results (max 100)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db)
):
    """
    Get swap transaction history for a user.
    
    Returns paginated list of swap transactions with status and amounts.
    """
    return swap_service.get_swap_history(address, chain, limit, offset, db)
