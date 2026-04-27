import base64
import io
import secrets

import pyotp
import qrcode
import requests

from app_pkg.repositories.auth_repository import (
    add_whitelist_ip,
    build_redis_client,
    get_app_api_key,
    get_saved_mfa_secret,
    load_whitelist_ips,
    persist_mfa_secret,
)

redis_client = build_redis_client()


def is_redis_available():
    return redis_client is not None


def get_real_ip(request):
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.headers.get('X-Real-IP', request.remote_addr or '0.0.0.0')


def fetch_geo_from_ip(ip):
    try:
        response = requests.get(f'https://whois.pconline.com.cn/ipJson.jsp?ip={ip}&json=true', timeout=8)
        response.encoding = 'utf-8'
        data = response.json()
        return data.get('ip'), data.get('pro'), data.get('city'), data.get('addr')
    except Exception:
        return None


def handle_login_failure(client_id):
    if not is_redis_available():
        return False, '密码或验证码错误'
    key = f'login_attempts:{client_id}'
    attempts = redis_client.incr(key)
    if attempts == 1:
        redis_client.expire(key, 24 * 3600)
    remaining = max(0, 5 - attempts)
    if attempts >= 5:
        redis_client.setex(f'blacklist:{client_id}', 24 * 3600, '1')
        redis_client.delete(key)
        return True, '❌ 密码或验证码错误次数过多，该设备已被封禁 24 小时'
    return False, f'密码或验证码错误，还可尝试 {remaining} 次'


def clear_login_attempts(client_id):
    if is_redis_available():
        redis_client.delete(f'login_attempts:{client_id}')


def is_blacklisted(client_id):
    return bool(is_redis_available() and redis_client.exists(f'blacklist:{client_id}'))


def load_whitelist():
    return load_whitelist_ips()


def add_ip_to_whitelist(ip):
    return add_whitelist_ip(ip)


def build_mfa_setup_context():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name='CloudManagerAdmin', issuer_name='CloudManager')
    img = qrcode.make(uri)
    buffered = io.BytesIO()
    img.save(buffered)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return {'secret': secret, 'qr_code': img_str}


def verify_mfa_code(secret, code):
    return pyotp.TOTP(secret).verify(code)


def save_verified_mfa_secret(secret):
    persist_mfa_secret(secret)


def current_mfa_secret():
    return get_saved_mfa_secret()


def fetch_api_key():
    return get_app_api_key()
