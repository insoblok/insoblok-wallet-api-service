from fastapi import FastAPI, Request, status, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from routers import evm, common, swap, receiving, xrp
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from services.networks import evm as evm_service
from database import get_db, engine
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv
import os

load_dotenv()

scheduler = BackgroundScheduler()

def scheduled_task():
    print("Task executed")
    evm_service.update_transaction_status()
# Base.metadata.create_all(bind=engine)
app = FastAPI(title="Non-Custodial Wallet API")

# Add exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return detailed validation errors"""
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": errors,
            "body": exc.body if hasattr(exc, 'body') else None
        }
    )

# Include Routers
app.include_router(evm.router, prefix="/evm", tags=["Ethereum/EVM"])
app.include_router(swap.router, prefix="/swap", tags=["Swap"])
app.include_router(common.router, prefix="/common", tags=["Common"])
app.include_router(receiving.router, prefix="/receiving", tags=["Receiving"])
app.include_router(xrp.router, prefix="/xrp", tags=["XRP"])

@app.get("/")
def root():
    return {"message": "Wallet backend is running"}

@app.get("/health")
def health_check():
    """Health check endpoint for App Engine and load balancers"""
    return {"status": "healthy", "service": "wallet-backend"}

@app.get("/ready")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness check endpoint - verifies database connectivity.
    App Engine will use this to determine if the instance is ready to serve traffic.
    """
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "database": "disconnected", "error": str(e)}
        )

@app.get("/_ah/warmup")
def warmup():
    """
    App Engine warmup handler.
    This endpoint is called by App Engine to warm up instances before routing traffic.
    """
    try:
        # Pre-initialize database connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "warmed up"}
    except Exception as e:
        # Even if warmup fails, return success to prevent App Engine from retrying
        # The /ready endpoint will handle actual readiness checks
        return {"status": "warmup attempted", "note": "may need more time"}

# @app.on_event("startup")
# async def startup_event():
#     # asyncio.create_task(watch_blocks())
#     watch_blocks()

@app.on_event("startup")
async def startup_event():
    # Schedule tasks to run at specific intervals
    scheduler.add_job(
        scheduled_task,
        # trigger=CronTrigger.from_crontab("*/5 * * * *"),  # Every 5 minutes
        trigger=IntervalTrigger(seconds=int(os.getenv("TRANSACTION_STATUS_UPDATE_PERIOD_SECONDS", "30"))),
        id="scheduled_task",
        replace_existing=True,
    )
    scheduler.start()