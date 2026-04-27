from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv('APP_DATA_DIR', PROJECT_ROOT / 'data')).resolve()


RUNTIME_FILES = {
    'config': 'config.json',
    'profiles': 'oci_profiles.json',
    'database': 'oci_tasks.db',
    'telegram': 'tg_settings.json',
    'cloudflare': 'cloudflare_settings.json',
    'default_key': 'default_key.json',
    'default_script': 'default_startup_script.sh',
    'xui': 'xui_settings.json',
    'mfa': 'mfa_secret.json',
}


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def data_path(name: str) -> str:
    ensure_data_dir()
    filename = RUNTIME_FILES[name]
    return str(DATA_DIR / filename)


def ensure_runtime_files():
    ensure_data_dir()
    text_defaults = {
        'default_script': '#!/bin/bash\n',
    }
    json_defaults = {
        'config': '{}\n',
        'profiles': '{\n  "profiles": {},\n  "profile_order": []\n}\n',
        'telegram': '{}\n',
        'cloudflare': '{}\n',
        'default_key': '{}\n',
        'xui': '{}\n',
        'mfa': '{}\n',
    }
    for key, content in json_defaults.items():
        path = Path(data_path(key))
        if not path.exists():
            path.write_text(content, encoding='utf-8')
    for key, content in text_defaults.items():
        path = Path(data_path(key))
        if not path.exists():
            path.write_text(content, encoding='utf-8')


__all__ = ['PROJECT_ROOT', 'DATA_DIR', 'RUNTIME_FILES', 'ensure_data_dir', 'data_path', 'ensure_runtime_files']
