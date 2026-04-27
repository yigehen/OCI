import json
import logging
import os

from app_pkg.core.runtime_paths import data_path

TG_CONFIG_FILE = data_path('telegram')
CLOUDFLARE_CONFIG_FILE = data_path('cloudflare')
DEFAULT_KEY_FILE = data_path('default_key')
DEFAULT_SCRIPT_FILE = data_path('default_script')
XUI_CONFIG_FILE = data_path('xui')


def _load_json_file(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}


def _save_json_file(path, payload, label):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
        logging.info(f'{label} saved to {path}')
    except Exception as e:
        logging.error(f'Failed to save {label}: {e}')


def load_tg_config():
    return _load_json_file(TG_CONFIG_FILE)


def save_tg_config(config):
    _save_json_file(TG_CONFIG_FILE, config, 'Telegram config')


def load_cloudflare_config():
    return _load_json_file(CLOUDFLARE_CONFIG_FILE)


def save_cloudflare_config(config):
    _save_json_file(CLOUDFLARE_CONFIG_FILE, config, 'Cloudflare config')


def load_xui_config():
    return _load_json_file(XUI_CONFIG_FILE)


def save_xui_config(config):
    _save_json_file(XUI_CONFIG_FILE, config, 'X-UI config')


def load_default_script():
    if not os.path.exists(DEFAULT_SCRIPT_FILE):
        return ''
    try:
        with open(DEFAULT_SCRIPT_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logging.error(f'Error reading default script: {e}')
        return ''


def save_default_script(script_content):
    try:
        with open(DEFAULT_SCRIPT_FILE, 'w', encoding='utf-8') as f:
            f.write(script_content)
        logging.info(f'Default startup script saved to {DEFAULT_SCRIPT_FILE}')
    except Exception as e:
        logging.error(f'Error saving default script: {e}')
        raise
