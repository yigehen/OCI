import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("PANEL_PASSWORD", "test-password")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/15")

    modules_to_reload = [
        "app_pkg.core.runtime_paths",
        "app_pkg.core.config_store",
        "app_pkg.repositories.integration_settings",
        "app_pkg.repositories.auth_repository",
        "app_pkg.services.auth_service",
        "app_pkg.web.auth_routes",
        "blueprints.oci_panel",
        "app_pkg",
    ]
    for name in modules_to_reload:
        if name in sys.modules:
            importlib.reload(sys.modules[name])

    from app_pkg import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def logged_in_client(client):
    with client.session_transaction() as sess:
        sess["user_logged_in"] = True
        sess["login_ip"] = "127.0.0.1"
        sess["device_id"] = "test-device"
        sess["login_region"] = "test-region"
    return client


def write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_get_tg_config_returns_only_configuration_status(logged_in_client, tmp_path, monkeypatch):
    write_json(tmp_path / "tg_settings.json", {"bot_token": "123456:abcdefghijklmnopqrstuvwxyz", "chat_id": "999"})

    response = logged_in_client.get("/oci/api/tg-config")
    data = response.get_json()

    assert response.status_code == 200
    assert data["chat_id"] == "999"
    assert data["bot_token_configured"] is True
    assert "bot_token" not in data


def test_get_cloudflare_config_returns_only_configuration_status(logged_in_client, tmp_path):
    write_json(tmp_path / "cloudflare_settings.json", {"api_token": "cf_super_secret_token_value", "zone_id": "zone123", "domain": "example.com"})

    response = logged_in_client.get("/oci/api/cloudflare-config")
    data = response.get_json()

    assert response.status_code == 200
    assert data["zone_id"] == "zone123"
    assert data["domain"] == "example.com"
    assert data["api_token_configured"] is True
    assert "api_token" not in data


def test_get_xui_config_returns_only_configuration_status(logged_in_client, tmp_path):
    write_json(tmp_path / "xui_settings.json", {"manager_url": "https://xui.example.com", "manager_secret": "xui_secret_123456"})

    response = logged_in_client.get("/oci/api/xui-config")
    data = response.get_json()

    assert response.status_code == 200
    assert data["manager_url"] == "https://xui.example.com"
    assert data["manager_secret_configured"] is True
    assert "manager_secret" not in data


def test_get_app_api_key_returns_only_configuration_status(logged_in_client, tmp_path):
    write_json(tmp_path / "config.json", {"api_secret_key": "abcdef0123456789abcdef0123456789"})

    response = logged_in_client.get("/api/get-app-api-key")
    data = response.get_json()

    assert response.status_code == 200
    assert data["api_key_configured"] is True
    assert "api_key" not in data
