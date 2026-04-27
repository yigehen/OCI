import os
import secrets


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_urlsafe(48)
    PANEL_PASSWORD = os.getenv('PANEL_PASSWORD', 'change-me-now')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() in {'true', '1', 't'}
    PERMANENT_SESSION_LIFETIME_HOURS = int(os.getenv('PERMANENT_SESSION_LIFETIME_HOURS', '24'))
