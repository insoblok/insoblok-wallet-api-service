from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import sqlalchemy
import os
import warnings

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Check if using local database or cloud database
# Default to local database for easier local development
USE_LOCAL_DB = os.getenv("USE_LOCAL_DB", "true").lower() == "true"
USE_CLOUD_DB = os.getenv("USE_CLOUD_DB", "false").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL")  # Optional: full connection string

# Clean DATABASE_URL - remove empty strings and whitespace
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.strip()
    if not DATABASE_URL:  # Empty string after stripping
        DATABASE_URL = None

# Prioritize DATABASE_URL - if it exists, always use it (Render.com, Heroku, etc.)
# This prevents accidentally using Google Cloud SQL when a DATABASE_URL is provided
# NEVER use Google Cloud SQL if DATABASE_URL is set
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
    # This block should only execute if:
    # 1. USE_CLOUD_DB is explicitly set to "true"
    # 2. DATABASE_URL is NOT set (None or empty)
    # 3. USE_LOCAL_DB is false or not set
    
    # Wrap entire Google Cloud SQL setup in try-except to fail gracefully
    try:
        from google.cloud.sql.connector import Connector, IPTypes
        
        DB_USER = os.getenv("DB_USER", "postgres")
        DB_PASS = os.getenv("DB_PASSWORD", "")
        DB_NAME = os.getenv("DB_NAME", "crypto_wallet")
        INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")
        
        if not INSTANCE_CONNECTION_NAME:
            raise ValueError("INSTANCE_CONNECTION_NAME is required when using cloud database.")
        
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
        # If Google Cloud SQL fails for ANY reason (auth, import, config, etc.),
        # fall back to local database connection
        error_msg = str(e).lower()
        
        if "credentials" in error_msg or "authentication" in error_msg:
            warnings.warn(
                f"Google Cloud authentication failed: {e}. "
                "Falling back to local database. Set USE_CLOUD_DB=false to suppress this warning.",
                UserWarning
            )
        elif "import" in error_msg or "not found" in error_msg:
            warnings.warn(
                f"Google Cloud SQL connector not available: {e}. "
                "Falling back to local database. Set USE_CLOUD_DB=false to suppress this warning.",
                UserWarning
            )
        else:
            warnings.warn(
                f"Google Cloud SQL setup failed: {e}. "
                "Falling back to local database. Set USE_CLOUD_DB=false to suppress this warning.",
                UserWarning
            )
        
        # Fall back to local database
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
            pool_pre_ping=True,
            pool_recycle=3600,
        )
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
