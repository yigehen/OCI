import json
import os

from app_pkg.core.runtime_paths import data_path

CONFIG_FILE = data_path('config')


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=4, ensure_ascii=False)
