from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from app_pkg.core.config_store import load_config, save_config
from app_pkg.services.auth_service import (
    add_ip_to_whitelist,
    build_mfa_setup_context,
    clear_login_attempts,
    current_mfa_secret,
    fetch_api_key,
    fetch_geo_from_ip,
    get_real_ip,
    handle_login_failure,
    is_blacklisted,
    load_whitelist,
    save_verified_mfa_secret,
    verify_mfa_code,
)
from app_pkg.tasks.oci_tasks import init_db as init_oci_db

auth_bp = Blueprint('auth', __name__)
TRUSTED_WHITELIST_IPS = []


def initialize_app_config():
    config = load_config()
    if 'api_secret_key' not in config or not config.get('api_secret_key'):
        import secrets
        config['api_secret_key'] = secrets.token_hex(32)
        save_config(config)
    return config


def install_auth_hooks(app):
    global TRUSTED_WHITELIST_IPS
    initialize_app_config()
    TRUSTED_WHITELIST_IPS = load_whitelist()

    @app.before_request
    def make_session_permanent():
        nonlocal app
        global TRUSTED_WHITELIST_IPS
        session.permanent = True
        if 'user_logged_in' not in session:
            return

        current_ip = get_real_ip(request)
        if current_ip in TRUSTED_WHITELIST_IPS:
            session['login_ip'] = current_ip
            return

        current_device_id = request.cookies.get('fp_device_id', 'Unknown')
        last_ip = session.get('login_ip')
        last_device_id = session.get('device_id')
        login_region = session.get('login_region', '未知区域')

        if last_ip == current_ip:
            return

        if last_device_id and last_device_id == current_device_id:
            current_geo = fetch_geo_from_ip(current_ip)
            current_region = f"{current_geo[2]}-{current_geo[3]}" if current_geo else '未知区域'
            if current_region == login_region or '未知' in current_region:
                session['login_ip'] = current_ip
                return

        session.clear()
        return redirect(url_for('auth.login'))

    with app.app_context():
        init_oci_db()


@auth_bp.route('/setup-mfa', methods=['GET', 'POST'])
def setup_mfa():
    if not session.get('pre_mfa_auth'):
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        secret = session.get('temp_mfa_secret')
        code = request.form.get('code')
        if verify_mfa_code(secret, code):
            save_verified_mfa_secret(secret)
            session['user_logged_in'] = True
            client_ip = get_real_ip(request)
            session['login_ip'] = client_ip
            session['device_id'] = request.cookies.get('fp_device_id', 'Unknown_Device')
            geo = fetch_geo_from_ip(client_ip)
            session['login_region'] = f"{geo[2]}-{geo[3]}" if geo else '未知区域'
            session.pop('pre_mfa_auth', None)
            session.pop('temp_mfa_secret', None)
            return redirect(url_for('auth.index'))
        return render_template('mfa_setup.html', error='验证码错误，请重试', secret=secret, qr_code=session.get('temp_mfa_qr'))

    ctx = build_mfa_setup_context()
    session['temp_mfa_secret'] = ctx['secret']
    session['temp_mfa_qr'] = ctx['qr_code']
    return render_template('mfa_setup.html', secret=ctx['secret'], qr_code=ctx['qr_code'])


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    client_ip = get_real_ip(request)
    client_id = request.cookies.get('fp_device_id') or client_ip

    if is_blacklisted(client_id):
        return render_template('login.html', error='❌ 该设备因多次尝试失败已被暂时封禁，请 24 小时后再试。'), 403

    if request.method == 'POST':
        password = request.form.get('password')
        mfa_code = request.form.get('mfa_code')
        form_device_id = request.form.get('device_id')
        if form_device_id:
            client_id = form_device_id

        if password == current_app.config['PANEL_PASSWORD']:
            secret = current_mfa_secret()
            if secret:
                if not mfa_code:
                    return render_template('login.html', error='请输入二次验证码', mfa_enabled=True)
                if verify_mfa_code(secret, mfa_code):
                    clear_login_attempts(client_id)
                    session.clear()
                    session['user_logged_in'] = True
                    session['login_ip'] = client_ip
                    session['device_id'] = client_id
                    geo = fetch_geo_from_ip(client_ip)
                    session['login_region'] = f"{geo[2]}-{geo[3]}" if geo else '未知区域'
                    return redirect(url_for('auth.index'))
                _, err = handle_login_failure(client_id)
                return render_template('login.html', error=err, mfa_enabled=True)

            clear_login_attempts(client_id)
            session.clear()
            session['pre_mfa_auth'] = True
            return redirect(url_for('auth.setup_mfa'))

        _, err = handle_login_failure(client_id)
        return render_template('login.html', error=err, mfa_enabled=current_mfa_secret() is not None)

    return render_template('login.html', mfa_enabled=current_mfa_secret() is not None)


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/')
def index():
    if 'user_logged_in' not in session:
        return redirect(url_for('auth.login'))
    return redirect(url_for('oci.oci_index'))


@auth_bp.route('/api/get-app-api-key')
def get_app_api_key():
    if 'user_logged_in' not in session:
        return jsonify({'error': '用户未登录'}), 401
    api_key = fetch_api_key()
    if api_key:
        return jsonify({'api_key_configured': True})
    return jsonify({'error': '未能在服务器上找到或配置API密钥。'}), 500


@auth_bp.route('/api/add-whitelist', methods=['POST'])
def add_whitelist():
    global TRUSTED_WHITELIST_IPS
    if 'user_logged_in' not in session:
        return jsonify({'success': False, 'error': '用户未登录'}), 401
    data = request.get_json() or {}
    target_ip = data.get('ip')
    if not target_ip:
        return jsonify({'success': False, 'error': '未提供 IP 地址'}), 400
    added = add_ip_to_whitelist(target_ip)
    TRUSTED_WHITELIST_IPS = load_whitelist()
    if added:
        return jsonify({'success': True, 'msg': f'✅ IP [{target_ip}] 已成功加入白名单！此后该 IP 登录将免受一切限制。'})
    return jsonify({'success': True, 'msg': '该 IP 已经在白名单中，无需重复添加。'})
