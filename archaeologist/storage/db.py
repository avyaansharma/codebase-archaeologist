import os
from contextlib import contextmanager
from typing import Generator
from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./archaeologist.db")

# Configure engine with multi-thread support and SQLite optimizations
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True
)

def init_db():
    """Initializes the database schema and enables SQLite WAL mode for high concurrency."""
    SQLModel.metadata.create_all(engine)
    if DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
        except Exception as e:
            print(f"Notice: Could not set SQLite PRAGMA WAL mode: {e}")

def get_session() -> Session:
    """Returns a new SQLModel database session."""
    return Session(engine)

@contextmanager
def get_session_context() -> Generator[Session, None, None]:
    """Context manager yielding a session with automatic rollback on error and closure."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
