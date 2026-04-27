import os

import redis

from app_pkg.core.config_store import load_config, save_config
from app_pkg.core.mfa import get_mfa_secret, save_mfa_secret

REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')


def build_redis_client():
    try:
        client = redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def load_whitelist_ips():
    return load_config().get('whitelist_ips', [])


def add_whitelist_ip(ip):
    config = load_config()
    whitelist = config.get('whitelist_ips', [])
    if ip not in whitelist:
        whitelist.append(ip)
        config['whitelist_ips'] = whitelist
        save_config(config)
        return True
    return False


def get_app_api_key():
    return load_config().get('api_secret_key')


def get_saved_mfa_secret():
    return get_mfa_secret()


def persist_mfa_secret(secret):
    save_mfa_secret(secret)
