import os, json, threading, string, random, base64, time, logging, uuid, sqlite3, datetime, signal, requests
from flask import Blueprint, render_template, jsonify, request, session, g, redirect, url_for, current_app
from functools import wraps
from pypinyin import lazy_pinyin
from datetime import timezone, timedelta
import oci
import re
from oci.core.models import (CreateVcnDetails, CreateSubnetDetails, CreateInternetGatewayDetails,
                             UpdateRouteTableDetails, RouteRule, CreatePublicIpDetails, CreateIpv6Details,
                             LaunchInstanceDetails, CreateVnicDetails, InstanceSourceViaImageDetails,
                             LaunchInstanceShapeConfigDetails, UpdateSecurityListDetails, EgressSecurityRule, IngressSecurityRule,
                             UpdateInstanceDetails, UpdateBootVolumeDetails, UpdateInstanceShapeConfigDetails,
                             AddVcnIpv6CidrDetails, UpdateSubnetDetails,
                             LaunchInstanceAgentConfigDetails, InstanceAgentPluginConfigDetails,
                             GetPublicIpByPrivateIpIdDetails, CreatePrivateIpDetails
                             )
from oci.exceptions import ServiceError
from extensions import celery
from app_pkg.core.runtime_paths import data_path

# --- Blueprint Setup ---
oci_bp = Blueprint('oci', __name__, template_folder='../../templates', static_folder='../../static')

# --- Configuration ---
KEYS_FILE = data_path('profiles')
DATABASE = data_path('database')
TG_CONFIG_FILE = data_path('telegram')
CLOUDFLARE_CONFIG_FILE = data_path('cloudflare')
DEFAULT_KEY_FILE = data_path('default_key')
XUI_CONFIG_FILE = data_path('xui')
# ✨✨✨ 新增：默认开机脚本保存路径 ✨✨✨
DEFAULT_SCRIPT_FILE = data_path('default_script')

# --- Timeout Handling ---
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("请求超时")

def timeout(seconds):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # macOS/Flask 某些请求可能不在主线程中执行，signal 在非主线程不可用
            if threading.current_thread() is not threading.main_thread():
                return f(*args, **kwargs)
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            try:
                result = f(*args, **kwargs)
            finally:
                signal.alarm(0)
            return result
        return wrapper
    return decorator

# --- 核心函数区域 ---

def get_db_connection(timeout=3):
    conn = sqlite3.connect(DATABASE, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def get_db():
    db = getattr(g, '_oci_database', None)
    if db is None:
        db = g._oci_database = get_db_connection(timeout=3)
    return db

@oci_bp.teardown_request
def close_connection(exception):
    db = getattr(g, '_oci_database', None)
    if db is not None:
        db.close()

def update_db_schema():
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [info['name'] for info in cursor.fetchall()]
        if 'completed_at' not in columns:
            logging.info("Schema update: Adding 'completed_at' column to 'tasks' table.")
            cursor.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
            db.commit()
            logging.info("'completed_at' column added successfully.")
        db.close()
    except Exception as e:
        logging.error(f"Failed to update database schema: {e}")

def init_db():
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
    table_exists = cursor.fetchone()
    if not table_exists:
        print("Initializing OCI database table 'tasks'...")
        logging.info("OCI database file found, but 'tasks' table is missing. Creating table...")
        cursor.executescript("""
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, type TEXT, name TEXT, status TEXT NOT NULL,
            result TEXT, created_at TEXT, account_alias TEXT, completed_at TEXT
        );
        """)
        db.commit()
        logging.info("'tasks' table created successfully in OCI database.")
    else:
        update_db_schema()
    db.close()

def query_db(query, args=(), one=False):
    db = get_db_connection(timeout=20)
    cur = db.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    db.close()
    return (rv[0] if rv else None) if one else rv

def _db_execute_celery(query, params=()):
    db = get_db_connection(timeout=20)
    db.execute(query, params)
    db.commit()
    db.close()

def _create_task_entry(task_type, task_name, alias=None):
    db = get_db()
    task_id = str(uuid.uuid4())
    if alias is None: alias = session.get('oci_profile_alias') or g.get('api_selected_alias', 'N/A')
    utc_time = datetime.datetime.now(timezone.utc).isoformat()
    db.execute('INSERT INTO tasks (id, type, name, status, result, created_at, account_alias) VALUES (?, ?, ?, ?, ?, ?, ?)',
               (task_id, task_type, task_name, 'pending', '', utc_time, alias))
    db.commit()
    return task_id

def load_profiles():
    if not os.path.exists(KEYS_FILE): return {"profiles": {}, "profile_order": []}
    try:
        with open(KEYS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            data = json.loads(content) if content else {"profiles": {}, "profile_order": []}
            if "profiles" not in data:
                data = {"profiles": data, "profile_order": list(data.keys())}
            if "profile_order" not in data:
                data["profile_order"] = list(data["profiles"].keys())
            return data
    except (IOError, json.JSONDecodeError): return {"profiles": {}, "profile_order": []}

def recover_snatching_tasks():
    logging.info("--- 检查并恢复被中断的抢占任务 ---")
    db = get_db_connection()
    try:
        orphaned_tasks = db.execute(
            "SELECT id, result, account_alias FROM tasks WHERE status = 'running' AND type = 'snatch'"
        ).fetchall()

        if not orphaned_tasks:
            logging.info("没有需要自动恢复的抢占任务。")
            return

        logging.info(f"发现 {len(orphaned_tasks)} 个需要自动恢复的抢占任务。")
        profiles = load_profiles().get("profiles", {})

        for task in orphaned_tasks:
            task_id = task['id']
            alias = task['account_alias']
            
            profile_config = profiles.get(alias)
            if not profile_config:
                logging.warning(f"任务 {task_id} 对应的账号 '{alias}' 配置已不存在，无法恢复。")
                db.execute(
                    "UPDATE tasks SET status = ?, result = ? WHERE id = ?",
                    ('failure', '任务因关联的账号配置被删除而恢复失败。', task_id)
                )
                db.commit()
                continue

            try:
                result_json = json.loads(task['result'])
                original_details = result_json.get('details')
                if not original_details:
                    raise ValueError("在任务 result 中未找到 'details' 字段。")
                
                result_json['last_message'] = "服务重启，任务已自动恢复并继续执行..."
                new_run_id = str(uuid.uuid4())
                result_json['run_id'] = new_run_id
                
                db.execute(
                    "UPDATE tasks SET result = ? WHERE id = ?",
                    (json.dumps(result_json), task_id)
                )
                db.commit()
                
                auto_bind_domain = original_details.get('auto_bind_domain', False)
                _snatch_instance_task.delay(task_id, profile_config, alias, original_details, new_run_id, auto_bind_domain)

                logging.info(f"已成功重新派发任务 {task_id} (账号: {alias})。")

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logging.error(f"解析或恢复任务 {task_id} 失败: {e}。")
                db.execute(
                    "UPDATE tasks SET status = ?, result = ? WHERE id = ?",
                    ('failure', f'任务恢复失败，原因: 无法解析任务参数 ({e})', task_id)
                )
                db.commit()

    except Exception as e:
        logging.error(f"在恢复抢占任务过程中发生未知错误: {e}")
    finally:
        db.close()
        logging.info("--- 抢占任务恢复检查完成 ---")

def _format_timedelta(duration: timedelta) -> str:
    seconds = duration.total_seconds()
    if seconds < 60:
        return f"{int(seconds)}秒"
    
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{int(days)}天")
    if hours > 0:
        parts.append(f"{int(hours)}小时")
    if minutes > 0:
        parts.append(f"{int(minutes)}分钟")
        
    return "".join(parts) if parts else "不到1分钟"

def save_profiles(data):
    with open(KEYS_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def _internal_fetch_and_save_tenancy_date(alias):
    try:
        all_data = load_profiles()
        profiles = all_data.get("profiles", {})
        if alias not in profiles:
            return False, "Profile not found"

        profile_config = profiles[alias]
        
        clients, error = get_oci_clients(profile_config, validate=False)
        if error:
            return False, error
            
        identity_client = clients['identity']
        tenancy_id = profile_config['tenancy']

        compartment = identity_client.get_compartment(compartment_id=tenancy_id).data
        created_at = compartment.time_created
        
        date_str = created_at.strftime('%Y-%m-%d')
        
        all_data["profiles"][alias]['registration_date'] = date_str
        save_profiles(all_data)
        
        logging.info(f"Successfully updated registration date for {alias}: {date_str}")
        return True, date_str
    except Exception as e:
        logging.error(f"Failed to fetch/save tenancy age for {alias}: {e}")
        return False, str(e)


def _auto_open_firewall(vnet_client, subnet_id, task_id=None):
    """
    检查指定子网的安全列表，如果没有允许所有流量的规则，则自动添加。
    """
    try:
        subnet = vnet_client.get_subnet(subnet_id).data
        # 遍历该子网关联的所有安全列表（通常只有一个默认的）
        for sl_id in subnet.security_list_ids:
            sl = vnet_client.get_security_list(sl_id).data
            
            # 检查是否已存在“允许所有”入站规则 (Source: 0.0.0.0/0, Protocol: all)
            ingress_exists = any(r.source == "0.0.0.0/0" and r.protocol == "all" for r in sl.ingress_security_rules)
            
            # 检查是否已存在“允许所有”出站规则 (Destination: 0.0.0.0/0, Protocol: all)
            egress_exists = any(r.destination == "0.0.0.0/0" and r.protocol == "all" for r in sl.egress_security_rules)

            if ingress_exists and egress_exists:
                logging.info(f"安全列表 {sl.display_name} 已包含允许所有规则，无需修改。")
                continue 

            # 准备更新列表
            new_ingress_rules = list(sl.ingress_security_rules)
            if not ingress_exists:
                if task_id: _db_execute_celery('UPDATE tasks SET result=? WHERE id=?', ('正在自动添加防火墙入站规则...', task_id))
                new_ingress_rules.append(IngressSecurityRule(
                    source="0.0.0.0/0", protocol="all", is_stateless=False, source_type="CIDR_BLOCK"
                ))
            
            new_egress_rules = list(sl.egress_security_rules)
            if not egress_exists:
                if task_id: _db_execute_celery('UPDATE tasks SET result=? WHERE id=?', ('正在自动添加防火墙出站规则...', task_id))
                new_egress_rules.append(EgressSecurityRule(
                    destination="0.0.0.0/0", protocol="all", is_stateless=False, destination_type="CIDR_BLOCK"
                ))

            # 提交更新
            vnet_client.update_security_list(
                sl_id, 
                UpdateSecurityListDetails(
                    ingress_security_rules=new_ingress_rules, 
                    egress_security_rules=new_egress_rules
                )
            )
            logging.info(f"已自动更新安全列表 {sl.display_name} 的防火墙规则。")
            
        return "✅ 防火墙已自动开放 (入站/出站)"
    except Exception as e:
        logging.error(f"自动开放防火墙失败: {e}")
        return f"⚠️ 防火墙自动开放失败: {str(e)[:50]}"

def load_tg_config():
    from app_pkg.repositories.integration_settings import load_tg_config as _load_tg_config
    return _load_tg_config()


def save_tg_config(config):
    from app_pkg.repositories.integration_settings import save_tg_config as _save_tg_config
    return _save_tg_config(config)


def load_cloudflare_config():
    from app_pkg.repositories.integration_settings import load_cloudflare_config as _load_cloudflare_config
    return _load_cloudflare_config()


def save_cloudflare_config(config):
    from app_pkg.repositories.integration_settings import save_cloudflare_config as _save_cloudflare_config
    return _save_cloudflare_config(config)


def load_xui_config():
    from app_pkg.repositories.integration_settings import load_xui_config as _load_xui_config
    return _load_xui_config()


def save_xui_config(config):
    from app_pkg.repositories.integration_settings import save_xui_config as _save_xui_config
    return _save_xui_config(config)


def _update_cloudflare_dns(subdomain, ip_address, record_type='A'):
    from app_pkg.services.cloudflare_service import update_cloudflare_dns
    return update_cloudflare_dns(subdomain, ip_address, record_type)

def send_tg_notification(message):
    from app_pkg.services.notification_service import send_tg_notification as _send_tg_notification
    return _send_tg_notification(message)

def generate_oci_password(length=16):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def get_oci_clients(profile_config, validate=True):
    from app_pkg.services.oci_clients import get_oci_clients as _get_oci_clients
    return _get_oci_clients(profile_config, validate)

def _ensure_subnet_in_profile(task_id, alias, vnet_client, tenancy_ocid):
    from app_pkg.services.oci_network_service import ensure_subnet_in_profile
    return ensure_subnet_in_profile(task_id, alias, vnet_client, tenancy_ocid, load_profiles, save_profiles, _db_execute_celery)

def get_user_data(password=None, startup_script=None, enable_password_auth=False):
    # ✨✨✨ 修改核心：在开机第一步就强制修复网络路由，专治甲骨文下载卡死 ✨✨✨
    default_script = """
echo "=== [Network Fix] Forcing IPv4 for GitHub to prevent Oracle IPv6 hang ==="
echo "140.82.113.3 github.com" >> /etc/hosts
echo "185.199.108.133 raw.githubusercontent.com" >> /etc/hosts
echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4
alias wget='wget -4'

echo "Waiting for apt lock to be released..."
while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do
   echo "Another apt/dpkg process is running. Waiting 10 seconds..."
   sleep 10
done

echo "Starting package installation with retries..."
for i in 1 2 3; do
  apt-get update && apt-get install -y curl wget unzip git socat cron && break
  echo "APT commands failed (attempt $i/3), retrying in 15 seconds..."
  sleep 15
done
"""
    
    script_parts = ["#cloud-config"]

    # 设置 root 密码
    if enable_password_auth and password:
        script_parts.extend([
            "chpasswd:",
            "  expire: False",
            "  list:",
            f"    - root:{password}"
        ])

    script_parts.append("runcmd:")
    
    # 开启 root SSH 登录权限
    if enable_password_auth:
        script_parts.append("  - \"sed -i -e '/^#*PasswordAuthentication/s/^.*$/PasswordAuthentication yes/' /etc/ssh/sshd_config\"")
        script_parts.append("  - \"sed -i -e '/^#*PermitRootLogin/s/^.*$/PermitRootLogin yes/' /etc/ssh/sshd_config\"")
    else:
        script_parts.append("  - \"sed -i -e '/^#*PasswordAuthentication/s/^.*$/PasswordAuthentication no/' /etc/ssh/sshd_config\"")
        script_parts.append("  - \"sed -i -e '/^#*PermitRootLogin/s/^.*$/PermitRootLogin yes/' /etc/ssh/sshd_config\"")

    script_parts.append("  - 'rm -f /etc/ssh/sshd_config.d/60-cloudimg-settings.conf'")
    
    # 复制公钥给 root，确保密钥模式下 root 也能直接登录
    script_parts.append("  - 'mkdir -p /root/.ssh && cp /home/ubuntu/.ssh/authorized_keys /root/.ssh/authorized_keys && chown root:root /root/.ssh/authorized_keys'")

    script_parts.append(f"  - [ bash, -c, {json.dumps(default_script)} ]")

    if startup_script and startup_script.strip():
        script_parts.append(f"  - [ bash, -c, {json.dumps(startup_script.strip())} ]")

    script_parts.append("  - systemctl restart sshd || service sshd restart || service ssh restart")

    script = "\n".join(script_parts)
    return base64.b64encode(script.encode('utf-8')).decode('utf-8')

def _enable_ipv6_networking(task_id, vnet_client, vnic_id):
    from app_pkg.services.oci_network_service import enable_ipv6_networking
    return enable_ipv6_networking(task_id, vnet_client, vnic_id, _db_execute_celery)

# --- Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_logged_in" in session:
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            if token == current_app.config.get('PANEL_API_KEY'):
                return f(*args, **kwargs)
        
        if request.path.startswith('/oci/api/'):
            return jsonify({"error": "用户未登录或API密钥无效"}), 401
        return redirect(url_for('auth.login'))
    return decorated_function

def oci_clients_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        alias = session.get('oci_profile_alias') or g.get('api_selected_alias')

        if not alias:
             return jsonify({"error": "请先选择一个OCI账号"}), 403

        profile_config = load_profiles().get("profiles", {}).get(alias)
        if not profile_config: return jsonify({"error": f"账号 '{alias}' 未找到"}), 404
        
        clients, error = get_oci_clients(profile_config, validate=False)
        if error: return jsonify({"error": error}), 500
        
        g.oci_clients = clients
        g.oci_config = profile_config
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---
@oci_bp.route("/")
@login_required
def oci_index():
    return render_template("oci.html")

# --- API Routes ---
@oci_bp.route('/api/default-ssh-key', methods=['GET', 'POST'])
@login_required
def default_ssh_key_handler():
    if request.method == 'GET':
        try:
            if os.path.exists(DEFAULT_KEY_FILE):
                with open(DEFAULT_KEY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return jsonify(data)
            return jsonify({'key': ''})
        except (IOError, json.JSONDecodeError):
            return jsonify({'key': ''})

    elif request.method == 'POST':
        data = request.json
        key = data.get('key', '').strip()
        if not key.startswith('ssh-rsa'):
            return jsonify({"error": "无效的 SSH 公钥格式。"}), 400
        try:
            with open(DEFAULT_KEY_FILE, 'w', encoding='utf-8') as f:
                json.dump({'key': key}, f, indent=4)
            return jsonify({"success": True, "message": "全局默认公钥已成功保存！"})
        except IOError as e:
            logging.error(f"保存默认公钥失败: {e}")
            return jsonify({"error": "保存默认公钥文件时出错。"}), 500

@oci_bp.route('/api/tg-config', methods=['GET', 'POST'])
@login_required
def tg_config_handler():
    if request.method == 'GET':
        config = load_tg_config()
        return jsonify({
            'chat_id': config.get('chat_id', ''),
            'bot_token_configured': bool(config.get('bot_token')),
        })
    elif request.method == 'POST':
        data = request.json
        bot_token, chat_id = data.get('bot_token', '').strip(), data.get('chat_id', '').strip()
        if not bot_token or not chat_id:
            return jsonify({"error": "Bot Token 和 Chat ID 不能为空"}), 400
        save_tg_config({'bot_token': bot_token, 'chat_id': chat_id})
        return jsonify({"success": True, "message": "Telegram 设置已保存"})

@oci_bp.route('/api/cloudflare-config', methods=['GET', 'POST'])
@login_required
def cloudflare_config_handler():
    if request.method == 'GET':
        config = load_cloudflare_config()
        return jsonify({
            'zone_id': config.get('zone_id', ''),
            'domain': config.get('domain', ''),
            'api_token_configured': bool(config.get('api_token')),
        })
    elif request.method == 'POST':
        data = request.json
        api_token = data.get('api_token', '').strip()
        zone_id = data.get('zone_id', '').strip()
        domain = data.get('domain', '').strip()
        if not all([api_token, zone_id, domain]):
            return jsonify({"error": "API 令牌, Zone ID 和主域名均不能为空"}), 400
        
        config = {'api_token': api_token, 'zone_id': zone_id, 'domain': domain}
        save_cloudflare_config(config)
        return jsonify({"success": True, "message": "Cloudflare 设置已成功保存"})

@oci_bp.route('/api/xui-config', methods=['GET', 'POST'])
@login_required
def xui_config_handler():
    if request.method == 'GET':
        config = load_xui_config()
        return jsonify({
            'manager_url': config.get('manager_url', ''),
            'manager_secret_configured': bool(config.get('manager_secret')),
        })
    elif request.method == 'POST':
        data = request.json
        url = data.get('manager_url', '').strip()
        secret = data.get('manager_secret', '').strip()
        # 允许空值 (用于清空配置)
        config = {'manager_url': url, 'manager_secret': secret}
        save_xui_config(config)
        return jsonify({"success": True, "message": "X-UI 对接配置已保存"})

# ✨✨✨ 新增：管理服务器端默认开机脚本的 API ✨✨✨
@oci_bp.route('/api/default-script', methods=['GET', 'POST'])
@login_required
def default_script_handler():
    from app_pkg.repositories.integration_settings import load_default_script, save_default_script

    if request.method == 'GET':
        return jsonify({'script': load_default_script()})

    elif request.method == 'POST':
        data = request.json
        script_content = data.get('script', '')
        try:
            save_default_script(script_content)
            return jsonify({"success": True, "message": "服务器端默认开机脚本已保存"})
        except Exception as e:
            return jsonify({"error": f"保存失败: {e}"}), 500
# ----------------------------------------------------

@oci_bp.route("/api/profiles", methods=["GET", "POST"])
@login_required
def manage_profiles():
    all_data = load_profiles()
    profiles = all_data.get("profiles", {})
    
    if request.method == "GET":
        profile_order = all_data.get("profile_order", [])
        
        ordered_keys = [p for p in profile_order if p in profiles]
        missing_keys = [p for p in profiles if p not in profile_order]
        
        try:
            missing_keys.sort(key=lambda name: "".join(lazy_pinyin(name)).lower())
        except NameError:
            missing_keys.sort(key=lambda name: name.lower())
        except Exception as e:
            logging.warning(f"Sort failed: {e}")
            missing_keys.sort()
        
        final_order_keys = ordered_keys + missing_keys
        
        if final_order_keys != profile_order:
            all_data["profile_order"] = final_order_keys
            save_profiles(all_data)
            
        now = datetime.datetime.now(timezone.utc)
        response_list = []

        for alias in final_order_keys:
            p_data = profiles.get(alias, {})
            item = p_data.copy()
            item["alias"] = alias
            
            if 'registration_date' in p_data and p_data['registration_date']:
                try:
                    reg_date = datetime.datetime.strptime(p_data['registration_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    delta = now - reg_date
                    item['days_elapsed'] = delta.days
                except ValueError:
                    logging.warning(f"Invalid date format for {alias}: {p_data['registration_date']}")
                    item['days_elapsed'] = 0
                except Exception as e:
                    logging.error(f"Error calculating date for {alias}: {e}")

            response_list.append(item)
            
        return jsonify(response_list)

    if request.method == "POST":
        data = request.json
        alias, new_profile_data = data.get('alias'), data.get('profile_data', {})
        if not alias or not new_profile_data:
            return jsonify({"error": "Missing alias or profile_data"}), 400
        
        is_new_profile = alias not in profiles
        
        updated_profile = profiles.get(alias, {})
        updated_profile.update(new_profile_data)

        if not updated_profile.get('default_ssh_public_key'):
            try:
                if os.path.exists(DEFAULT_KEY_FILE):
                    with open(DEFAULT_KEY_FILE, 'r', encoding='utf-8') as f:
                        key_data = json.load(f)
                        updated_profile['default_ssh_public_key'] = key_data.get('key', "")
                else:
                    updated_profile['default_ssh_public_key'] = ""
            except (IOError, json.JSONDecodeError):
                updated_profile['default_ssh_public_key'] = ""
        
        all_data["profiles"][alias] = updated_profile
        
        if is_new_profile:
            if "profile_order" not in all_data:
                all_data["profile_order"] = []
            if alias not in all_data["profile_order"]:
                 all_data["profile_order"].append(alias)
                 
        save_profiles(all_data)
        
        try:
            threading.Thread(target=_internal_fetch_and_save_tenancy_date, args=(alias,)).start()
        except Exception:
            pass
            
        return jsonify({"success": True, "alias": alias})

@oci_bp.route("/api/profiles/order", methods=["POST"])
@login_required
def save_profile_order():
    data = request.json
    new_order = data.get('order')
    if not isinstance(new_order, list):
        return jsonify({"error": "Invalid order data"}), 400
    
    all_data = load_profiles()
    all_data['profile_order'] = new_order
    save_profiles(all_data)
    
    return jsonify({"success": True, "message": "Account order saved."})

@oci_bp.route("/api/profiles/<alias>", methods=["GET", "DELETE"])
@login_required
def handle_single_profile(alias):
    all_data = load_profiles()
    profiles = all_data.get("profiles", {})
    
    if alias not in profiles: return jsonify({"error": "账号未找到"}), 404
    
    if request.method == "GET":
        profile_data = profiles[alias].copy()
        try:
            clients, error = get_oci_clients(profile_data, validate=False)
            if not error and clients and clients.get('identity'):
                identity_client = clients['identity']

                user_id = profile_data.get('user')
                if user_id:
                    try:
                        user_obj = identity_client.get_user(user_id=user_id).data
                        profile_data['user_display_name'] = getattr(user_obj, 'email', None) or getattr(user_obj, 'name', None) or user_id
                    except Exception as e:
                        logging.warning(f"Failed to fetch OCI user display name for {alias}: {e}")

                tenancy_id = profile_data.get('tenancy')
                if tenancy_id:
                    try:
                        tenancy_obj = identity_client.get_tenancy(tenancy_id=tenancy_id).data
                        profile_data['tenancy_display_name'] = getattr(tenancy_obj, 'name', None) or tenancy_id
                    except Exception:
                        try:
                            tenancy_compartment = identity_client.get_compartment(compartment_id=tenancy_id).data
                            profile_data['tenancy_display_name'] = getattr(tenancy_compartment, 'name', None) or tenancy_id
                        except Exception as e:
                            logging.warning(f"Failed to fetch OCI tenancy display name for {alias}: {e}")
        except Exception as e:
            logging.warning(f"Failed to enrich profile detail for {alias}: {e}")

        return jsonify(profile_data)
    
    if request.method == "DELETE":
        del all_data["profiles"][alias]
        if "profile_order" in all_data and alias in all_data["profile_order"]:
            all_data["profile_order"].remove(alias)
            
        save_profiles(all_data)
        
        if session.get('oci_profile_alias') == alias: session.pop('oci_profile_alias', None)
        return jsonify({"success": True})

@oci_bp.route('/api/tasks/snatching/running', methods=['GET'])
@login_required
def get_running_snatching_tasks():
    try:
        tasks = query_db("SELECT id, name, result, created_at, account_alias, status FROM tasks WHERE type = 'snatch' AND status IN ('running', 'paused') ORDER BY created_at DESC")
        tasks_list = []
        for task in tasks:
            task_dict = dict(task)
            try:
                task_dict['result'] = json.loads(task_dict['result'])
            except (json.JSONDecodeError, TypeError):
                pass
            tasks_list.append(task_dict)
        return jsonify(tasks_list)
    except Exception as e: return jsonify({"error": str(e)}), 500

@oci_bp.route('/api/tasks/snatching/completed', methods=['GET'])
@login_required
def get_completed_snatching_tasks():
    tasks = query_db("SELECT id, name, status, result, created_at, completed_at, account_alias FROM tasks WHERE type = 'snatch' AND (status = 'success' OR status = 'failure') ORDER BY created_at DESC LIMIT 50")
    return jsonify([dict(task) for task in tasks])

@oci_bp.route('/api/tasks/<task_id>', methods=['DELETE'])
@login_required
def delete_task_record(task_id):
    db = get_db()
    task = db.execute("SELECT status FROM tasks WHERE id = ?", [task_id]).fetchone()
    if task and task['status'] in ['success', 'failure', 'paused']:
        celery.control.revoke(task_id, terminate=True, signal='SIGKILL')
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        db.commit()
        return jsonify({"success": True, "message": "任务记录已删除。"})
    return jsonify({"error": "只能删除已完成、失败或暂停的任务记录。"}), 400

@oci_bp.route('/api/tasks/<task_id>/stop', methods=['POST'])
@login_required
def stop_task(task_id):
    celery.control.revoke(task_id, terminate=True, signal='SIGKILL')
    
    task_data = query_db('SELECT result FROM tasks WHERE id = ?', [task_id], one=True)
    if task_data and task_data['result']:
        try:
            result_json = json.loads(task_data['result'])
            result_json['last_message'] = '任务已被用户手动暂停。'
            if 'run_id' in result_json:
                del result_json['run_id']
            new_result = json.dumps(result_json)
        except (json.JSONDecodeError, TypeError):
            new_result = '{"last_message": "任务已被用户手动暂停。"}'
    else:
        new_result = '{"last_message": "任务已被用户手动暂停。"}'
        
    _db_execute_celery('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('paused', new_result, task_id))
    return jsonify({"success": True, "message": f"任务 {task_id} 已被暂停。"})

@oci_bp.route('/api/tasks/resume', methods=['POST'])
@login_required
def resume_tasks():
    data = request.json
    task_ids = data.get('task_ids', [])
    if not task_ids:
        return jsonify({"error": "未提供任何任务ID"}), 400

    resumed_count = 0
    failed_tasks = []
    profiles = load_profiles().get("profiles", {})
    
    for task_id in task_ids:
        task = query_db('SELECT result, account_alias FROM tasks WHERE id = ? AND status = ?', [task_id, 'paused'], one=True)
        if not task:
            failed_tasks.append(task_id)
            continue
        
        alias = task['account_alias']
        profile_config = profiles.get(alias)

        if not profile_config:
            failed_tasks.append(task_id)
            _db_execute_celery("UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?", ('failure', '任务因关联的账号配置被删除而恢复失败。', datetime.datetime.now(timezone.utc).isoformat(), task_id))
            continue

        try:
            result_json = json.loads(task['result'])
            original_details = result_json.get('details')
            if not original_details:
                raise ValueError("任务数据中缺少 'details' 字段")
            
            result_json['last_message'] = "任务已手动恢复，继续执行..."
            new_run_id = str(uuid.uuid4())
            result_json['run_id'] = new_run_id

            _db_execute_celery('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', json.dumps(result_json), task_id))
            
            auto_bind_domain = original_details.get('auto_bind_domain', False)
            _snatch_instance_task.delay(task_id, profile_config, alias, original_details, new_run_id, auto_bind_domain)

            resumed_count += 1
        except Exception as e:
            logging.error(f"恢复任务 {task_id} 失败: {e}")
            failed_tasks.append(task_id)
            _db_execute_celery('UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?', ('failure', f'手动恢复任务失败: {e}', datetime.datetime.now(timezone.utc).isoformat(), task_id))

    message = f"成功恢复 {resumed_count} 个任务。"
    if failed_tasks:
        message += f" {len(failed_tasks)} 个任务恢复失败: {', '.join(failed_tasks)}"
    
    return jsonify({"success": True, "message": message})

@oci_bp.route("/api/session", methods=["POST", "GET", "DELETE"])
@login_required
@timeout(20)
def oci_session_route():
    try:
        if request.method == "POST":
            alias = request.json.get("alias")
            profiles = load_profiles().get("profiles", {})
            if not alias or alias not in profiles: return jsonify({"error": "无效的账号别名"}), 400
            
            profile_config = profiles.get(alias)
            session['oci_profile_alias'] = alias
            g.api_selected_alias = alias

            _, error = get_oci_clients(profile_config, validate=True)
            if error:
                session.pop('oci_profile_alias', None)
                g.pop('api_selected_alias', None)
                return jsonify({"error": f"连接验证失败: {error}"}), 400
            
            if 'registration_date' not in profile_config:
                logging.info(f"No registration date found locally for {alias}, fetching from API in background...")
                threading.Thread(target=_internal_fetch_and_save_tenancy_date, args=(alias,)).start()
            else:
                logging.info(f"Local registration date found for {alias} ({profile_config['registration_date']}), skipping API fetch.")

            proxy_info = profile_config.get('proxy')
            if proxy_info:
                success_message = f"连接成功! 当前账号: {alias} (通过代理: {proxy_info})"
            else:
                success_message = f"连接成功! 当前账号: {alias} (未使用代理)"

            can_create = bool(profile_config.get('default_ssh_public_key'))
            return jsonify({
                "success": True, 
                "alias": alias, 
                "can_create": can_create,
                "message": success_message
            })

        if request.method == "GET":
            alias = session.get('oci_profile_alias')
            if alias:
                can_create = bool(load_profiles().get("profiles", {}).get(alias, {}).get('default_ssh_public_key'))
                return jsonify({"logged_in": True, "alias": alias, "can_create": can_create})
            return jsonify({"logged_in": False})
        if request.method == "DELETE":
            session.pop('oci_profile_alias', None)
            g.pop('api_selected_alias', None)
            return jsonify({"success": True})
    except TimeoutException:
        session.pop('oci_profile_alias', None)
        g.pop('api_selected_alias', None)
        return jsonify({"error": "连接 OCI 验证超时，请检查网络或API密钥设置。"}), 504
    except Exception as e:
        session.pop('oci_profile_alias', None)
        g.pop('api_selected_alias', None)
        return jsonify({"error": str(e)}), 500

@oci_bp.route('/api/instances', defaults={'alias': None})
@oci_bp.route('/api/<alias>/instances')
@login_required
@timeout(45)
def get_instances(alias):
    try:
        if alias is None:
            alias = session.get('oci_profile_alias')
            if not alias:
                return jsonify({"error": "请先选择一个OCI账号"}), 403

        profile_config = load_profiles().get("profiles", {}).get(alias)
        if not profile_config:
            return jsonify({"error": f"账号 '{alias}' 未找到"}), 404
        clients, error = get_oci_clients(profile_config, validate=False)
        if error:
            return jsonify({"error": error}), 500
        
        from app_pkg.services.oci_compute_service import list_instance_details
        instance_details_list = list_instance_details(profile_config, clients)
        return jsonify(instance_details_list)
    except TimeoutException:
        return jsonify({"error": "获取实例列表超时，请稍后重试。"}), 504
    except Exception as e:
        return jsonify({"error": f"获取实例列表失败: {e}"}), 500

@oci_bp.route('/api/<alias>/tenancy-age')
@login_required
@timeout(15)
def get_tenancy_age(alias):
    try:
        profiles = load_profiles().get("profiles", {})
        if alias not in profiles:
            return jsonify({"error": "账号未找到"}), 404
        
        profile_config = profiles[alias]
        clients, error = get_oci_clients(profile_config, validate=False)
        if error:
            return jsonify({"error": error}), 500
            
        identity_client = clients['identity']
        tenancy_id = profile_config['tenancy']

        compartment = identity_client.get_compartment(compartment_id=tenancy_id).data
        
        created_at = compartment.time_created
        now = datetime.datetime.now(timezone.utc)
        
        delta = now - created_at
        days_elapsed = delta.days
        date_str = created_at.strftime('%Y-%m-%d')
        
        return jsonify({
            "success": True,
            "registration_date": date_str,
            "days_elapsed": days_elapsed
        })

    except Exception as e:
        logging.error(f"Failed to fetch tenancy age for {alias}: {e}")
        return jsonify({"error": f"查询失败: {str(e)}"}), 500

@oci_bp.route('/api/instance-details/<instance_id>')
@login_required
@oci_clients_required
@timeout(10)
def get_instance_details(instance_id):
    try:
        from app_pkg.services.oci_compute_service import get_instance_detail_payload
        payload = get_instance_detail_payload(instance_id, g.oci_config, g.oci_clients)
        return jsonify(payload)
    except TimeoutException:
        return jsonify({"error": "获取实例详情超时，请稍后重试。"}), 504
    except Exception as e:
        return jsonify({"error": f"获取实例详情失败: {e}"}), 500


@oci_bp.route('/api/available-os-versions')
@login_required
@oci_clients_required
@timeout(20)
def get_available_os_versions():
    try:
        compute_client = g.oci_clients['compute']
        tenancy_ocid = g.oci_config['tenancy']
        
        logging.info("Fetching available OS versions...")
        
        # 设定你想获取的官方 OS 列表
        target_oses = ["Canonical Ubuntu", "Oracle Linux"]
        result = []
        
        for os_name in target_oses:
            images = oci.pagination.list_call_get_all_results(
                compute_client.list_images,
                compartment_id=tenancy_ocid,
                operating_system=os_name,
                sort_by="TIMECREATED",
                sort_order="DESC"
            ).data

            versions = set()
            for img in images:
                v = img.operating_system_version
                # 过滤掉精简版或带特殊架构后缀的版本，保持列表清爽
                if v and 'Minimal' not in v and 'aarch64' not in v:
                    versions.add(v)
            
            # 排序并取最新的 2 个版本
            sorted_versions = sorted(list(versions), reverse=True)[:2]
            for v in sorted_versions:
                result.append(f"{os_name}-{v}")
        
        return jsonify(result)

    except TimeoutException:
        return jsonify({"error": "获取操作系统列表超时。"}), 504
    except Exception as e:
        logging.error(f"Failed to get OS versions: {e}", exc_info=True)
        return jsonify({"error": f"获取操作系统列表失败: {e}"}), 500

@oci_bp.route('/api/available-shapes')
@login_required
@oci_clients_required
@timeout(45)
def get_available_shapes():
    try:
        os_name_version = request.args.get('os_name_version')
        if not os_name_version:
            return jsonify({"error": "缺少 os_name_version 参数"}), 400

        # 防止版本号带有 '-' 导致 split 报错
        os_name, os_version = os_name_version.split('-', 1)
        compute_client = g.oci_clients['compute']
        tenancy_ocid = g.oci_config['tenancy']
        
        # ==========================================
        # 核心逻辑：自动检测账号是否为升级号 (PAYG)
        # ==========================================
        is_upgraded = False
        try:
            limits_client = oci.limits.LimitsClient(g.oci_config)
            proxy_url = g.oci_config.get('proxy')
            if proxy_url:
                limits_client.base_client.session.proxies = {'http': proxy_url, 'https': proxy_url}
                
            # ✨ 修复点：必须先获取可用域 (AD)，因为 CPU 配额是 AD 级别的限制
            identity_client = g.oci_clients['identity']
            ads = identity_client.list_availability_domains(tenancy_ocid).data
            ad_name = ads[0].name if ads else None

            if ad_name:
                # 查询 Compute 服务的配额限制，必须带上 availability_domain
                limits = oci.pagination.list_call_get_all_results(
                    limits_client.list_limit_values,
                    compartment_id=tenancy_ocid,
                    service_name="compute",
                    availability_domain=ad_name
                ).data
                
                for limit in limits:
                    # 付费号的 standard-core-count 或 E3/E4 等常规实例核心配额一定会大于 0
                    # 免费号这些付费机型核心数全为 0 (只有 a1-core-count 和 micro-core-count)
                    if limit.name in ["standard-core-count", "standard-e4-core-count", "standard-e3-core-count"]:
                        if limit.value > 0:
                            is_upgraded = True
                            break
            else:
                is_upgraded = True # 获取不到 AD，防误杀，直接放行
                
        except Exception as e:
            logging.warning(f"检测账号配额失败，为防误杀，默认按升级号处理: {e}")
            is_upgraded = True 
        # ==========================================
        
        logging.info(f"Fetching shapes for {os_name} {os_version}... (is_upgraded={is_upgraded})")
        
        # 获取该操作系统的最新镜像，取前几个就能覆盖 ARM 和 x86 架构
        images = compute_client.list_images(
            compartment_id=tenancy_ocid,
            operating_system=os_name,
            operating_system_version=os_version,
            sort_by="TIMECREATED",
            sort_order="DESC",
            limit=10
        ).data

        valid_shapes = set()
        checked_images = 0
        
        for img in images:
            if checked_images >= 3: 
                break
            try:
                compat_entries = oci.pagination.list_call_get_all_results(
                    compute_client.list_image_shape_compatibility_entries,
                    image_id=img.id
                ).data
                
                found_shapes = False
                for entry in compat_entries:
                    shape = entry.shape
                    if shape.startswith('VM.Standard'):
                        # --- 核心过滤逻辑：如果不是升级号，只允许加入免费规格 ---
                        if not is_upgraded:
                            if shape not in ['VM.Standard.A1.Flex', 'VM.Standard.E2.1.Micro']:
                                continue
                        # ----------------------------------------------------
                        valid_shapes.add(shape)
                        found_shapes = True
                if found_shapes:
                    checked_images += 1
            except Exception as e:
                logging.warning(f"Failed to get compat entries for image {img.id}: {e}")

        valid_shapes_list = list(valid_shapes)
        # 排序：A1.Flex 和 E2.1.Micro 永远在最前面
        valid_shapes_list.sort(key=lambda s: (0 if 'A1.Flex' in s else 1 if 'E2.1.Micro' in s else 2, s))

        return jsonify(valid_shapes_list)

    except TimeoutException:
        return jsonify({"error": "获取可用实例规格超时。"}), 504
    except Exception as e:
        logging.error(f"Failed to get available shapes: {e}", exc_info=True)
        return jsonify({"error": f"获取可用实例规格失败: {e}"}), 500

@oci_bp.route('/api/update-instance', methods=['POST'])
@login_required
@oci_clients_required
@timeout(10)
def update_instance():
    try:
        data = request.json
        action, instance_id = data.get('action'), data.get('instance_id')
        if not action or not instance_id: return jsonify({"error": "缺少 action 或 instance_id"}), 400
        task_name = f"{action} on instance {instance_id[-6:]}"
        task_id = _create_task_entry('action', task_name)
        _update_instance_details_task.delay(task_id, g.oci_config, data)
        return jsonify({"message": f"'{action}' 请求已提交...", "task_id": task_id})
    except (sqlite3.OperationalError, TimeoutException) as e:
        if isinstance(e, TimeoutException) or "database is locked" in str(e):
            return jsonify({"error": "请求超时或数据库繁忙，请稍后重-试。"}), 503
        raise
    except Exception as e:
        return jsonify({"error": f"提交实例更新任务失败: {e}"}), 500

@oci_bp.route('/api/instance/add-secondary-ip', methods=['POST'])
@login_required
def add_secondary_ip():
    data = request.json
    alias = session.get('oci_profile_alias') or g.get('api_selected_alias')
    instance_id = data.get('instance_id')
    
    if not alias or not instance_id:
        return jsonify({'error': '缺少必要参数'}), 400

    try:
        profiles = load_profiles().get("profiles", {})
        profile_config = profiles.get(alias)
        if not profile_config:
            return jsonify({"error": f"账号 '{alias}' 未找到"}), 404

        clients, error = get_oci_clients(profile_config, validate=False)
        if error:
            return jsonify({"error": error}), 500
            
        compute_client = clients['compute']
        network_client = clients['vnet']
        config = profile_config

        vnic_attachments = oci.pagination.list_call_get_all_results(
            compute_client.list_vnic_attachments,
            compartment_id=config['tenancy'],
            instance_id=instance_id
        ).data
        
        if not vnic_attachments:
            return jsonify({'error': '找不到实例的网卡信息'}), 404
            
        vnic_id = vnic_attachments[0].vnic_id

        private_ip_details = CreatePrivateIpDetails(
            vnic_id=vnic_id,
            display_name="Auto-Panel-Secondary"
        )
        private_ip_response = network_client.create_private_ip(private_ip_details)
        new_private_ip = private_ip_response.data
        
        public_ip_details = CreatePublicIpDetails(
            compartment_id=config['tenancy'],
            lifetime='RESERVED',
            private_ip_id=new_private_ip.id,
            display_name=f"PubIP-for-{new_private_ip.ip_address}"
        )
        
        public_ip_response = network_client.create_public_ip(public_ip_details)
        new_public_ip = public_ip_response.data

        ip_addr = new_private_ip.ip_address
        
        yaml_content = (
            "network:\\\\n"
            "  version: 2\\\\n"
            "  ethernets:\\\\n"
            "    $IFACE:\\\\n"
            "      addresses:\\\\n"
            f"        - {ip_addr}/24"
        )
        
        cmd_hint = (
            f"IFACE=$(ip route get 1 | awk '{{print $5;exit}}'); "
            f"sudo printf \"{yaml_content}\" | sudo tee /etc/netplan/99-secondary-ip-{ip_addr.replace('.', '-')}.yaml > /dev/null; "
            f"sudo netplan apply; "
            f"echo '✅ IP {ip_addr} added successfully!'"
        )

        return jsonify({
            'message': 'IP 附加成功！',
            'private_ip': new_private_ip.ip_address,
            'public_ip': new_public_ip.ip_address,
            'cmd_hint': cmd_hint
        })

    except ServiceError as e:
        return jsonify({'error': f"OCI API 错误: {e.message}"}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@oci_bp.route('/api/instance/delete-secondary-ip', methods=['POST'])
@login_required
@oci_clients_required
@timeout(15)
def delete_secondary_ip():
    try:
        data = request.json
        private_ip_id = data.get('private_ip_id')
        
        if not private_ip_id:
            return jsonify({"error": "缺少 private_ip_id 参数"}), 400

        vnet_client = g.oci_clients['vnet']

        try:
            private_ip_obj = vnet_client.get_private_ip(private_ip_id).data
            if private_ip_obj.is_primary:
                return jsonify({"error": "无法删除主私有 IP。"}), 400
        except ServiceError as se:
            if se.status == 404:
                return jsonify({"error": "IP 地址不存在或已被删除。"}), 404
            raise

        vnet_client.delete_private_ip(private_ip_id)
        return jsonify({"success": True, "message": "IP 删除请求已提交（立即生效）。"})

    except ServiceError as e:
        return jsonify({'error': f"OCI API 错误: {e.message}"}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@oci_bp.route('/api/instance/delete-ipv6', methods=['POST'])
@login_required
@oci_clients_required
@timeout(15)
def delete_ipv6():
    try:
        data = request.json
        ipv6_id = data.get('ipv6_id')
        
        if not ipv6_id:
            return jsonify({"error": "缺少 ipv6_id 参数"}), 400

        vnet_client = g.oci_clients['vnet']
        vnet_client.delete_ipv6(ipv6_id)
        
        return jsonify({"success": True, "message": "IPv6 删除请求已提交（立即生效）。"})

    except ServiceError as e:
        return jsonify({'error': f"OCI API 错误: {e.message}"}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@oci_bp.route('/api/instance-action', methods=['POST'], defaults={'alias': None})
@oci_bp.route('/api/<alias>/instance-action', methods=['POST'])
@login_required
@timeout(10)
def instance_action(alias):
    try:
        if alias is None:
            alias = session.get('oci_profile_alias')
            if not alias:
                return jsonify({"error": "请先选择一个OCI账号"}), 403

        from app_pkg.services.oci_task_submission_service import SubmissionError, submit_instance_action

        payload = submit_instance_action(alias, request.json)
        return jsonify(payload)
    except SubmissionError as e:
        return jsonify({"error": e.message}), e.status_code
    except (sqlite3.OperationalError, TimeoutException) as e:
        if isinstance(e, TimeoutException) or "database is locked" in str(e):
            return jsonify({"error": "请求超时或数据库繁忙，请稍后重试。"}), 503
        raise
    except Exception as e:
        return jsonify({"error": f"提交实例操作失败: {e}"}), 500

@oci_bp.route('/api/network/resources')
@login_required
@oci_clients_required
@timeout(45)
def get_network_resources():
    try:
        vnet_client = g.oci_clients['vnet']
        tenancy_ocid = g.oci_config['tenancy']
        
        vcns = oci.pagination.list_call_get_all_results(
            vnet_client.list_vcns,
            compartment_id=tenancy_ocid
        ).data
        
        network_data = []
        for vcn in vcns:
            if vcn.lifecycle_state != 'AVAILABLE':
                continue
            
            security_lists = oci.pagination.list_call_get_all_results(
                vnet_client.list_security_lists,
                compartment_id=tenancy_ocid,
                vcn_id=vcn.id
            ).data
            
            sl_list = [
                {"id": sl.id, "display_name": sl.display_name}
                for sl in security_lists
                if sl.lifecycle_state == 'AVAILABLE'
            ]
            
            if sl_list:
                network_data.append({
                    "vcn_id": vcn.id,
                    "vcn_name": vcn.display_name,
                    "security_lists": sorted(sl_list, key=lambda x: x['display_name'])
                })
                
        return jsonify(sorted(network_data, key=lambda x: x['vcn_name']))
    except TimeoutException:
        return jsonify({"error": "获取网络资源列表超时。"}), 504
    except Exception as e:
        return jsonify({"error": f"获取网络资源失败: {e}"}), 500

@oci_bp.route('/api/network/security-list/<security_list_id>')
@login_required
@oci_clients_required
@timeout(20)
def get_security_list_details(security_list_id):
    try:
        vnet_client = g.oci_clients['vnet']
        security_list = vnet_client.get_security_list(security_list_id).data
        return jsonify(json.loads(str(security_list)))
    except TimeoutException:
        return jsonify({"error": "获取安全列表详情超时。"}), 504
    except Exception as e:
        return jsonify({"error": f"获取安全列表详情失败: {e}"}), 500

@oci_bp.route('/api/network/update-security-rules', methods=['POST'])
@login_required
@oci_clients_required
@timeout(10)
def update_security_rules():
    try:
        data = request.json
        security_list_id, rules = data.get('security_list_id'), data.get('rules')
        if not security_list_id or not rules: return jsonify({"error": "缺少 security_list_id 或 rules"}), 400
        vnet_client = g.oci_clients['vnet']

        def parse_port_range(pr_dict):
            if not pr_dict: return None
            return oci.core.models.PortRange(min=pr_dict.get('min'), max=pr_dict.get('max'))

        def parse_options(opt_dict, opt_class):
            if not opt_dict: return None
            return opt_class(
                destination_port_range=parse_port_range(opt_dict.get('destination_port_range')),
                source_port_range=parse_port_range(opt_dict.get('source_port_range'))
            )

        ingress_rules = []
        for r in rules.get('ingress_security_rules', []):
            rule = IngressSecurityRule(
                is_stateless=r.get('is_stateless', False),
                protocol=r.get('protocol'),
                source=r.get('source'),
                source_type=r.get('source_type', 'CIDR_BLOCK'),
                tcp_options=parse_options(r.get('tcp_options'), oci.core.models.TcpOptions),
                udp_options=parse_options(r.get('udp_options'), oci.core.models.UdpOptions)
            )
            ingress_rules.append(rule)

        egress_rules = []
        for r in rules.get('egress_security_rules', []):
            rule = EgressSecurityRule(
                is_stateless=r.get('is_stateless', False),
                protocol=r.get('protocol'),
                destination=r.get('destination'),
                destination_type=r.get('destination_type', 'CIDR_BLOCK'),
                tcp_options=parse_options(r.get('tcp_options'), oci.core.models.TcpOptions),
                udp_options=parse_options(r.get('udp_options'), oci.core.models.UdpOptions)
            )
            egress_rules.append(rule)

        update_details = UpdateSecurityListDetails(
            ingress_security_rules=ingress_rules,
            egress_security_rules=egress_rules
        )

        vnet_client.update_security_list(security_list_id, update_details)
        return jsonify({"success": True, "message": "安全规则已成功更新！"})
    except TimeoutException:
        return jsonify({"error": "更新安全规则超时，请稍后重试。"}), 504
    except Exception as e:
        return jsonify({"error": f"更新安全规则失败: {e}"}), 500

@oci_bp.route('/api/launch-instance', methods=['POST'], defaults={'alias': None, 'endpoint': 'launch-instance'})
@oci_bp.route('/api/<alias>/<endpoint>', methods=['POST'])
@login_required
@timeout(30)
def launch_instance(alias, endpoint):
    try:
        if endpoint not in ["create-instance", "snatch-instance", "launch-instance"]:
            return jsonify({"error": "无效的端点"}), 404

        if alias is None:
            alias = session.get('oci_profile_alias')
            if not alias:
                return jsonify({"error": "请先选择一个OCI账号"}), 403

        from app_pkg.services.oci_task_submission_service import SubmissionError, submit_launch_instance

        payload = submit_launch_instance(alias, request.json)
        return jsonify(payload)

    except SubmissionError as e:
        return jsonify({"error": e.message}), e.status_code
    except (sqlite3.OperationalError, TimeoutException) as e:
        if isinstance(e, TimeoutException) or "database is locked" in str(e):
            return jsonify({"error": "请求超时或数据库繁忙，请稍后重试。"}), 503
        raise
    except Exception as e:
        logging.error(f"提交抢占任务失败: {e}")
        return jsonify({"error": f"提交抢占任务失败: {e}"}), 500

@oci_bp.route('/api/task_status/<task_id>')
@login_required
def task_status(task_id):
    task = query_db('SELECT status, result, type FROM tasks WHERE id = ?', [task_id], one=True)
    if task:
        return jsonify({'status': task['status'], 'result': task['result'], 'type': task['type']})
    return jsonify({'status': 'not_found'}), 404

# --- Celery Tasks ---
@celery.task
def _update_instance_details_task(task_id, profile_config, data):
    from app_pkg.services.oci_instance_update_service import run_update_instance_details_task

    return run_update_instance_details_task(task_id, profile_config, data, _db_execute_celery)

# ==========================================
# ✨✨✨ 新增：IAM 身份与用户管理核心 API ✨✨✨
# ==========================================

@oci_bp.route('/api/identity/users', methods=['GET', 'POST'])
@login_required
@oci_clients_required
@timeout(30)
def handle_identity_users():
    from app_pkg.services.oci_identity_user_service import handle_identity_users_request

    payload, status_code = handle_identity_users_request(
        identity_client=g.oci_clients['identity'],
        tenancy_ocid=g.oci_config['tenancy'],
        method=request.method,
        data=request.json,
    )
    return jsonify(payload), status_code


@oci_bp.route('/api/identity/users/<user_id>/<action>', methods=['POST'])
@login_required
@oci_clients_required
@timeout(30)
def handle_user_actions(user_id, action):
    from app_pkg.services.oci_identity_user_service import handle_user_action_request

    payload, status_code = handle_user_action_request(
        identity_client=g.oci_clients['identity'],
        user_id=user_id,
        action=action,
        data=request.json,
    )
    return jsonify(payload), status_code

        

@celery.task
def _instance_action_task(task_id, profile_config, action, instance_id, data):
    from app_pkg.services.oci_instance_action_service import run_instance_action_task

    return run_instance_action_task(task_id, profile_config, action, instance_id, data, _db_execute_celery)

@celery.task
def _snatch_instance_task(task_id, profile_config, alias, details, run_id, auto_bind_domain=False):
    from app_pkg.services.oci_snatch_service import run_snatch_instance_task

    return run_snatch_instance_task(task_id, profile_config, alias, details, run_id, auto_bind_domain, _db_execute_celery)
