from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import sqlalchemy
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Check if using local database or cloud database
# Default to local database for easier local development
USE_LOCAL_DB = os.getenv("USE_LOCAL_DB", "true").lower() == "true"
USE_CLOUD_DB = os.getenv("USE_CLOUD_DB", "false").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL")  # Optional: full connection string

# Prioritize DATABASE_URL - if it exists, always use it (Render.com, Heroku, etc.)
# This prevents accidentally using Google Cloud SQL when a DATABASE_URL is provided
if DATABASE_URL:
    # Use DATABASE_URL (Render.com, Heroku, etc. provide this)
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
    )
elif USE_LOCAL_DB or not USE_CLOUD_DB:
    # Local PostgreSQL database connection (when DATABASE_URL is not provided)
    # Build connection string from individual components
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "crypto_wallet")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    
    # Create connection string for local PostgreSQL
    # Using psycopg2 driver (psycopg2-binary is in requirements.txt)
    connection_string = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(
        connection_string,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
    )
elif USE_CLOUD_DB and not DATABASE_URL:
    # Google Cloud SQL database connection (original implementation)
    # Only import and initialize when actually using cloud database
    # IMPORTANT: Never use Google Cloud SQL if DATABASE_URL is set (Render.com, Heroku, etc.)
    try:
        from google.cloud.sql.connector import Connector, IPTypes
    except ImportError as e:
        raise ImportError(
            "Google Cloud SQL connector is not installed. "
            "Install it with: pip install cloud-sql-python-connector pg8000. "
            "Or set USE_CLOUD_DB=false to use local database instead."
        ) from e
    except Exception as e:
        # If there's an authentication error, provide helpful message
        if "credentials" in str(e).lower() or "authentication" in str(e).lower():
            raise ValueError(
                "Google Cloud authentication failed. "
                "Set USE_CLOUD_DB=false to use local database instead, "
                "or configure Google Cloud credentials properly."
            ) from e
        raise
    
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "crypto_wallet")
    INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")
    
    if not INSTANCE_CONNECTION_NAME:
        raise ValueError("INSTANCE_CONNECTION_NAME is required when using cloud database. Set USE_CLOUD_DB=false to use local database instead.")
    
    try:
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
        
        # Create SQLAlchemy engine with the connector and connection pooling
        engine = sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=getconn,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,   # Recycle connections after 1 hour
        )
    except Exception as e:
        if "credentials" in str(e).lower() or "authentication" in str(e).lower():
            raise ValueError(
                f"Google Cloud authentication error: {e}. "
                "Set USE_CLOUD_DB=false and USE_LOCAL_DB=true to use local database instead."
            ) from e
        raise
else:
    # Fallback to local database if neither is explicitly set
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "crypto_wallet")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    
    connection_string = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(
        connection_string,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
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
