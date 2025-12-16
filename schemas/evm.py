from json import load
from pydantic import BaseModel, field_validator, Field
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import os

load_dotenv()

class BalanceRequest(BaseModel):
    chain: Optional[str] = Field(default="", description="Chain name: 'ethereum', 'sepolia', 'insoblok', or '' for all chains")
    address: str = Field(..., description="Ethereum wallet address (required, must start with 0x and be 42 characters)")
    token_symbol: Optional[str] = Field(default=None, description="Token symbol (optional)")
    decimals: Optional[int] = Field(default=None, description="Token decimals (optional)")
    
    @field_validator('address')
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate Ethereum address format"""
        if not v or not isinstance(v, str):
            raise ValueError("Address is required and must be a string")
        
        # Strip whitespace
        v = v.strip()
        
        if not v.startswith("0x"):
            raise ValueError("Address must start with '0x'")
        
        if len(v) != 42:
            raise ValueError("Address must be 42 characters (0x + 40 hex characters)")
        
        # Validate hex characters
        try:
            int(v[2:], 16)
        except ValueError:
            raise ValueError("Address must contain valid hexadecimal characters")
        
        return v
    
    @field_validator('chain')
    @classmethod
    def validate_chain(cls, v: Optional[str]) -> str:
        """Normalize chain value"""
        if v is None:
            return ""
        return str(v).strip()
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "chain": "ethereum",
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb5"
            }
        }
    }

class BalanceResponse(BaseModel):
    address: str
    chain: str
    token_address: Optional[str] = ""
    token_symbol: str
    balance: float
    updated_at: datetime

class TransactionRequest(BaseModel):
    chain: str
    signed_raw_tx: str  # hex string of signed tx
    from_address: str
    to_address: str
    token_symbol: str
    amount: float

class TransactionResponse(BaseModel):
    tx_hash: str
    status: str
    timestamp: datetime

class QuoteRequest(BaseModel):
    from_address: str
    to: str
    amount: float
    chain: str
    
class TransferRequest(BaseModel):
    sender: Optional[str]=str(os.getenv("ADDRESS"))
    recipient: str
    amount: float
    chain: str

class PublicKeyToAddressRequest(BaseModel):
    public_key: str  # Public key in hex format (with or without 0x prefix)