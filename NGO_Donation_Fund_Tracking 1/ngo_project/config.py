# ==========================================
# Project configuration file
# Stores database connection values and app settings.
# ==========================================
import os

# Base folder for this Flask project.
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Secret key protects the session and CSRF behavior.
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")

    # MySQL connection details for the NGO fund tracking database.
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
    MYSQL_USER = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "kaifjaman")
    MYSQL_DB = os.environ.get("MYSQL_DB", "ngo_fund_tracking")

    # Cookie security settings to help protect authenticated admin sessions.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"

    # Default pagination setting for list screens.
    ROWS_PER_PAGE = 15

    # Prefix used when creating donation receipts.
    RECEIPT_PREFIX = "NGO-RCPT"
