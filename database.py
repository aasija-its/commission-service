import struct
import pyodbc
from azure.identity import DefaultAzureCredential
from config import SQL_SERVER, SQL_DATABASE, SQL_PORT

_credential = DefaultAzureCredential()

def get_connection() -> pyodbc.Connection:
    """Return a new pyodbc connection authenticated via Azure AD Default."""
    token = _credential.get_token("https://database.windows.net/.default")
    token_bytes = token.token.encode("UTF-16-LE")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={SQL_SERVER},{SQL_PORT};"
        f"Database={SQL_DATABASE};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str, attrs_before={1256: token_struct})


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT query and return rows as a list of dicts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
