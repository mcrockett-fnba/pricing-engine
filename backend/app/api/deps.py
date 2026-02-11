from collections.abc import Generator

from app.db.connection import db_pool


def get_db() -> Generator:
    """FastAPI dependency that yields a DB connection and closes it after use."""
    conn = db_pool.get_connection()
    try:
        yield conn
    finally:
        conn.close()
