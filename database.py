from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from google.cloud.sql.connector import Connector, IPTypes
import sqlalchemy
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "crypto_wallet")
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")  

# Initialize Cloud SQL Connector
connector = Connector()

def getconn():
    return connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",  # driver
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type=IPTypes.PRIVATE if os.getenv("USE_PRIVATE_IP") == "true" else IPTypes.PUBLIC
    )

# Create SQLAlchemy engine with the connector
engine = sqlalchemy.create_engine(
    "postgresql+pg8000://",
    creator=getconn,
)

# Session and Base
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()