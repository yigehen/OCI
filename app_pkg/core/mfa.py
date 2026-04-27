import base64
import io
import json
import os

import pyotp
import qrcode

from app_pkg.core.runtime_paths import data_path

MFA_FILE = data_path('mfa')


def get_mfa_secret():
    if not os.path.exists(MFA_FILE):
        return None
    try:
        with open(MFA_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh).get('secret')
    except Exception:
        return None


def save_mfa_secret(secret):
    with open(MFA_FILE, 'w', encoding='utf-8') as fh:
        json.dump({'secret': secret}, fh)


def generate_mfa_setup_payload(name='OCIAdmin', issuer='OCI'):
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(name=name, issuer_name=issuer)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf)
    return secret, base64.b64encode(buf.getvalue()).decode()
