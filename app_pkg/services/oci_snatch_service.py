import datetime
import json
import logging
import random
import string
import time
from datetime import timedelta, timezone

import oci
from oci.core.models import (
    CreateVnicDetails,
    InstanceSourceViaImageDetails,
    LaunchInstanceDetails,
    LaunchInstanceShapeConfigDetails,
)
from oci.exceptions import ServiceError

from app_pkg.repositories.integration_settings import load_cloudflare_config, load_xui_config
from app_pkg.repositories.oci_profiles import load_profiles, save_profiles
from app_pkg.repositories.task_db import query_db
from app_pkg.services.cloudflare_service import update_cloudflare_dns
from app_pkg.services.notification_service import send_tg_notification
from app_pkg.services.oci_clients import get_oci_clients
from app_pkg.services.oci_network_service import ensure_subnet_in_profile, get_user_data


def generate_oci_password(length=16):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def format_timedelta(duration: timedelta) -> str:
    seconds = duration.total_seconds()
    if seconds < 60:
        return f'{int(seconds)}秒'
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours > 0:
        parts.append(f'{int(hours)}小时')
    if minutes > 0:
        parts.append(f'{int(minutes)}分钟')
    return ''.join(parts) if parts else '不到1分钟'


def auto_open_firewall(vnet_client, subnet_id, task_id=None):
    subnet = vnet_client.get_subnet(subnet_id).data
    security_list_ids = subnet.security_list_ids
    if not security_list_ids:
        return '⚠️ 子网没有关联任何安全列表，跳过自动放行。'

    changed_lists = []
    for sl_id in security_list_ids:
        sl = vnet_client.get_security_list(sl_id).data
        ingress_rules = list(sl.ingress_security_rules or [])
        egress_rules = list(sl.egress_security_rules or [])

        ingress_ok = any(getattr(rule, 'source', None) == '0.0.0.0/0' and getattr(rule, 'protocol', None) == 'all' for rule in ingress_rules)
        egress_ok = any(getattr(rule, 'destination', None) == '0.0.0.0/0' and getattr(rule, 'protocol', None) == 'all' for rule in egress_rules)

        if ingress_ok and egress_ok:
            continue

        from oci.core.models import EgressSecurityRule, IngressSecurityRule, UpdateSecurityListDetails

        if not ingress_ok:
            ingress_rules.append(IngressSecurityRule(source='0.0.0.0/0', protocol='all', source_type='CIDR_BLOCK', is_stateless=False))
        if not egress_ok:
            egress_rules.append(EgressSecurityRule(destination='0.0.0.0/0', protocol='all', destination_type='CIDR_BLOCK', is_stateless=False))

        vnet_client.update_security_list(
            sl_id,
            UpdateSecurityListDetails(ingress_security_rules=ingress_rules, egress_security_rules=egress_rules),
        )
        changed_lists.append(sl.display_name or sl_id)

    if changed_lists:
        return f'已自动放行安全列表: {", ".join(changed_lists)}'
    return '安全列表已允许公网流量，无需调整'


def run_snatch_instance_task(task_id, profile_config, alias, details, run_id, auto_bind_domain, db_execute):
    task_data = query_db('SELECT result FROM tasks WHERE id = ?', [task_id], one=True)
    try:
        status_data = json.loads(task_data['result']) if task_data and task_data['result'] else {}
    except (json.JSONDecodeError, TypeError):
        status_data = {}

    if not status_data or 'details' not in status_data:
        status_data['details'] = details
        status_data['start_time'] = datetime.datetime.now(timezone.utc).isoformat()
        status_data['attempt_count'] = 0
        status_data['last_message'] = '抢占任务准备中...'

    task_details = status_data.get('details', {})
    task_details.setdefault('boot_volume_size', 50)
    if task_details.get('shape') == 'VM.Standard.E2.1.Micro':
        task_details['ocpus'] = 1
        task_details['memory_in_gbs'] = 1
    status_data['details'] = task_details

    status_data['details']['account_alias'] = alias
    status_data['run_id'] = run_id
    db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', json.dumps(status_data), task_id))

    try:
        clients, error = get_oci_clients(profile_config, validate=False)
        if error:
            raise Exception(error)
        compute_client, identity_client, vnet_client = clients['compute'], clients['identity'], clients['vnet']

        tenancy_ocid = profile_config.get('tenancy')
        ssh_key = details.get('custom_ssh_key') or profile_config.get('default_ssh_public_key')
        if not ssh_key:
            raise Exception('未提供 SSH 公钥 (既无自定义公钥，账号也无默认公钥)')

        ad_objects = identity_client.list_availability_domains(tenancy_ocid).data
        if not ad_objects:
            raise Exception('无法获取可用性域列表。')
        availability_domains = [ad.name for ad in ad_objects]

        subnet_id = ensure_subnet_in_profile(task_id, alias, vnet_client, tenancy_ocid, load_profiles, save_profiles, db_execute)
        os_name, os_version = details['os_name_version'].split('-')
        shape = details['shape']

        status_data['last_message'] = '正在查找兼容的系统镜像...'
        db_execute('UPDATE tasks SET result = ? WHERE id = ?', (json.dumps(status_data), task_id))

        images = oci.pagination.list_call_get_all_results(
            compute_client.list_images,
            tenancy_ocid,
            operating_system=os_name,
            operating_system_version=os_version,
            shape=shape,
            sort_by='TIMECREATED',
            sort_order='DESC',
        ).data
        if not images:
            raise Exception(f'未找到适用于 {os_name} {os_version} 的兼容镜像')

        enable_password_auth = details.get('enable_password_auth', False)
        instance_password = None
        if enable_password_auth:
            user_provided_password = details.get('instance_password', '').strip()
            instance_password = user_provided_password or generate_oci_password()

        cf_config = load_cloudflare_config()
        cf_domain = cf_config.get('domain', '')

        xui_conf = load_xui_config()
        raw_url = xui_conf.get('manager_url', '').strip().rstrip('/')
        manager_secret = xui_conf.get('manager_secret', '')
        manager_url = f'{raw_url}/api/auto_register_node' if raw_url and not raw_url.endswith('/api/auto_register_node') else raw_url

        is_domain_bound = 'true' if auto_bind_domain else 'false'
        env_injection = f'''
export MAIN_DOMAIN="{cf_domain}"
export IS_DOMAIN_BOUND="{is_domain_bound}"
export MANAGER_URL="{manager_url}"
export AUTO_REG_SECRET="{manager_secret}"
'''
        original_script = details.get('startup_script', '')
        final_startup_script = env_injection + '\n' + original_script
        user_data_encoded = get_user_data(instance_password, final_startup_script, enable_password_auth)

        plugins_config_list = [
            oci.core.models.InstanceAgentPluginConfigDetails(name='Custom Logs Monitoring', desired_state='DISABLED')
        ]
        agent_config_details = oci.core.models.LaunchInstanceAgentConfigDetails(
            is_monitoring_disabled=True,
            is_management_disabled=False,
            plugins_config=plugins_config_list,
        )

        base_launch_details = {
            'compartment_id': tenancy_ocid,
            'shape': shape,
            'display_name': details.get('display_name_prefix', 'snatch-instance'),
            'create_vnic_details': CreateVnicDetails(subnet_id=subnet_id, assign_public_ip=True),
            'metadata': {'ssh_authorized_keys': ssh_key, 'user_data': user_data_encoded},
            'source_details': InstanceSourceViaImageDetails(image_id=images[0].id, boot_volume_size_in_gbs=details['boot_volume_size']),
            'shape_config': LaunchInstanceShapeConfigDetails(ocpus=details.get('ocpus'), memory_in_gbs=details.get('memory_in_gbs')) if 'Flex' in shape else None,
            'agent_config': agent_config_details,
        }
    except Exception as e:
        db_execute('UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?', ('failure', f'❌ 抢占任务准备阶段失败: {e}', datetime.datetime.now(timezone.utc).isoformat(), task_id))
        return

    last_update_time = time.time()
    attempt_count = status_data.get('attempt_count', 0)

    while True:
        current_task_data = query_db('SELECT result, status FROM tasks WHERE id = ?', [task_id], one=True)
        if not current_task_data:
            logging.warning(f'Task {task_id} not found in DB. Worker will exit.')
            return
        if current_task_data['status'] != 'running':
            logging.info(f"Task {task_id} status is '{current_task_data['status']}', not 'running'. Worker will exit.")
            return

        try:
            current_result_json = json.loads(current_task_data['result'])
            db_run_id = current_result_json.get('run_id')
            if db_run_id != run_id:
                logging.info(f'Task {task_id} has a new run_id ({db_run_id}). This worker ({run_id}) will exit.')
                return
        except (json.JSONDecodeError, TypeError, KeyError):
            logging.error(f'Could not verify run_id for task {task_id}. Data might be corrupt. Exiting.')
            db_execute('UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?', ('failure', '任务数据损坏，无法继续执行。', datetime.datetime.now(timezone.utc).isoformat(), task_id))
            return

        attempt_count += 1
        status_data['attempt_count'] = attempt_count
        force_update = False
        current_ad_index = (attempt_count - 1) % len(availability_domains)
        current_ad_name = availability_domains[current_ad_index]
        if 'details' not in status_data:
            status_data['details'] = {}
        status_data['details']['ad'] = current_ad_name

        try:
            launch_details_dict = base_launch_details.copy()
            launch_details_dict['availability_domain'] = current_ad_name
            launch_details = LaunchInstanceDetails(**launch_details_dict)

            status_data['last_message'] = f'正在 {current_ad_name} 中尝试...'
            db_execute('UPDATE tasks SET result = ? WHERE id = ?', (json.dumps(status_data), task_id))
            force_update = True

            instance = compute_client.launch_instance(launch_details).data
            status_data['last_message'] = f"第 {status_data['attempt_count']} 次尝试成功！实例 {instance.display_name} 正在置备..."
            db_execute('UPDATE tasks SET result = ? WHERE id = ?', (json.dumps(status_data), task_id))
            oci.wait_until(compute_client, compute_client.get_instance(instance.id), 'lifecycle_state', 'RUNNING', max_wait_seconds=600)

            public_ip = '获取中...'
            try:
                vnic_attachments = oci.pagination.list_call_get_all_results(compute_client.list_vnic_attachments, compartment_id=tenancy_ocid, instance_id=instance.id).data
                if vnic_attachments:
                    vnic = vnet_client.get_vnic(vnic_attachments[0].vnic_id).data
                    public_ip = vnic.public_ip or '无'
            except Exception:
                public_ip = '获取失败'

            firewall_msg = ''
            try:
                firewall_msg = auto_open_firewall(vnet_client, subnet_id, task_id)
            except Exception as fw_e:
                logging.error(f'Task {task_id} firewall auto-open error: {fw_e}')
                firewall_msg = f'⚠️ 防火墙自动开放异常: {str(fw_e)[:30]}'

            db_msg = f"🎉 抢占成功 (第 {status_data['attempt_count']} 次尝试)!\n- 实例名: {instance.display_name}\n- 可用区: {current_ad_name}\n- 公网IP: {public_ip}\n- 登陆用户名：root"
            if firewall_msg:
                db_msg += f'\n- {firewall_msg}'
            if enable_password_auth and instance_password:
                db_msg += f'\n- 密码：{instance_password}'
            else:
                db_msg += '\n- 登录方式: 仅 SSH 密钥'

            dns_update_msg = ''
            if auto_bind_domain and public_ip not in ['无', '获取失败']:
                dns_update_msg = update_cloudflare_dns(instance.display_name, public_ip, 'A')
                db_msg += f'\n{dns_update_msg}'

            db_execute('UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?', ('success', db_msg, datetime.datetime.now(timezone.utc).isoformat(), task_id))

            duration_str = '未知'
            try:
                start_time = datetime.datetime.fromisoformat(status_data['start_time'])
                end_time = datetime.datetime.now(timezone.utc)
                duration_str = format_timedelta(end_time - start_time)
            except (KeyError, TypeError):
                logging.warning(f'无法为任务 {task_id} 计算总用时。')

            result_for_tg = (
                f"🎉 抢占成功 (第 {status_data['attempt_count']} 次尝试)!\n"
                f'- 总用时: {duration_str}\n'
                f'- 实例名: {instance.display_name}\n'
                f'- 可用区: {current_ad_name}\n'
                f'- 公网IP: {public_ip}\n'
                f'- 登陆用户名: root'
            )
            if enable_password_auth and instance_password:
                result_for_tg += f'\n- 密码: {instance_password}'
            else:
                result_for_tg += '\n- 登录方式: 仅 SSH 密钥'
            if firewall_msg:
                result_for_tg += f'\n- {firewall_msg}'
            if dns_update_msg:
                result_for_tg += f'\n{dns_update_msg}'

            tg_msg = (
                f"🔔 *任务完成通知*\n\n"
                f"*账户*: `{alias}`\n"
                f"*任务名称*: `{details.get('display_name_prefix', 'snatch-instance')}`\n\n"
                f"*结果*:\n{result_for_tg}"
            )
            send_tg_notification(tg_msg)
            return
        except ServiceError as e:
            force_update = True
            if e.status == 429 or 'TooManyRequests' in e.code or 'Out of host capacity' in str(e.message) or 'LimitExceeded' in e.code:
                status_data['last_message'] = f'在 {current_ad_name} 中资源不足 ({e.code})'
            else:
                status_data['last_message'] = f'在 {current_ad_name} 中遇到API错误 ({e.code})'
        except Exception as e:
            force_update = True
            status_data['last_message'] = f'在 {current_ad_name} 中遇到未知错误 ({str(e)[:50]}...)'

        task_record_check = query_db('SELECT status FROM tasks WHERE id = ?', [task_id], one=True)
        if not task_record_check or task_record_check['status'] not in ['running', 'pending']:
            logging.info(f'Snatching task {task_id} has been stopped or paused. Exiting loop.')
            return

        delay = random.randint(details.get('min_delay', 30), details.get('max_delay', 90))
        status_data['last_message'] += f'，将在 {delay} 秒后重试...'
        current_time = time.time()
        if (current_time - last_update_time > 5) or force_update:
            db_execute('UPDATE tasks SET result = ? WHERE id = ?', (json.dumps(status_data), task_id))
            last_update_time = current_time
        time.sleep(delay)


__all__ = ['run_snatch_instance_task', 'generate_oci_password', 'format_timedelta', 'auto_open_firewall']
