import os

SQL_SERVER   = os.environ.get("SQL_SERVER",   "ssr-inc-lgz-sha-uat-wus2.database.windows.net")
SQL_DATABASE = os.environ.get("SQL_DATABASE", "sdb-inc-tms-web-uat-wus2")
SQL_PORT     = int(os.environ.get("SQL_PORT", 1433))

# APPLICATIONINSIGHTS_CONNECTION_STRING for telemetry (optional)
APPLICATIONINSIGHTS_CONNECTION_STRING = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")

# Default commission rates (overridable via API at runtime)
# Transportation reps earn a % of CustomerTotal revenue
DEFAULT_TRANSPORT_RATE = float(os.environ.get("DEFAULT_TRANSPORT_RATE", "0.02"))   # 2%
# Procurement reps earn a % of Margin
DEFAULT_PROCUREMENT_RATE = float(os.environ.get("DEFAULT_PROCUREMENT_RATE", "0.05"))  # 5%
