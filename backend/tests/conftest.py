import sys
from unittest.mock import MagicMock

# Mock pyodbc so tests can run without ODBC drivers installed
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
