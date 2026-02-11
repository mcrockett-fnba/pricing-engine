from __future__ import annotations

import logging
import time

try:
    import pyodbc
except ImportError:
    pyodbc = None

from app.config import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    """Manages pyodbc connections to SQL Server."""

    def __init__(self):
        self._conn_string: str = ""
        self._initialized: bool = False

    def initialize(self):
        self._conn_string = settings.SQLSERVER_CONN_STRING
        if self._conn_string:
            logger.info("Database pool initialized with connection string")
            self._initialized = True
        else:
            logger.warning("No SQLSERVER_CONN_STRING configured — DB calls will fail")

    def get_connection(self, retries: int = 3, delay: float = 1.0):
        """Get a database connection with retry logic."""
        if pyodbc is None:
            raise RuntimeError("pyodbc is not installed (missing ODBC driver)")
        if not self._initialized or not self._conn_string:
            raise RuntimeError("Database pool not initialized or connection string missing")

        last_error = None
        for attempt in range(1, retries + 1):
            try:
                conn = pyodbc.connect(self._conn_string, timeout=30)
                return conn
            except pyodbc.Error as e:
                last_error = e
                logger.warning("DB connection attempt %d/%d failed: %s", attempt, retries, e)
                if attempt < retries:
                    time.sleep(delay)

        raise RuntimeError(f"Failed to connect after {retries} attempts: {last_error}")

    def test_connection(self) -> dict:
        """Test DB connectivity and return status info."""
        if pyodbc is None:
            return {"status": "unavailable", "message": "pyodbc not installed"}
        if not self._initialized or not self._conn_string:
            return {"status": "not_configured", "message": "No connection string set"}
        try:
            conn = self.get_connection(retries=1)
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0]
            conn.close()
            return {"status": "connected", "version": version}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close(self):
        logger.info("Database pool closed")
        self._initialized = False


db_pool = DatabasePool()
