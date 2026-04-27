import datetime
import logging
import time
from datetime import timezone

import oci
from oci.core.models import CreateIpv6Details, CreatePublicIpDetails, GetPublicIpByPrivateIpIdDetails
from oci.exceptions import ServiceError

from app_pkg.services.cloudflare_service import update_cloudflare_dns
from app_pkg.services.notification_service import send_tg_notification
from app_pkg.services.oci_clients import get_oci_clients
from app_pkg.services.oci_network_service import enable_ipv6_networking


def _notify_task_result(success, alias, task_title, content, source):
    if source == 'web':
        return
    if success:
        tg_msg = (
            f"🔔 *任务完成通知*\n\n"
            f"*账户*: `{alias}`\n"
            f"*任务*: `{task_title}`\n\n"
            f"*结果*:\n{content}"
        )
    else:
        tg_msg = (
            f"🔔 *任务失败通知*\n\n"
            f"*账户*: `{alias}`\n"
            f"*任务*: `{task_title}`\n\n"
            f"*原因*:\n`{content}`"
        )
    send_tg_notification(tg_msg)


def run_instance_action_task(task_id, profile_config, action, instance_id, data, db_execute):
    db_execute(
        'UPDATE tasks SET status = ?, result = ? WHERE id = ?',
        ('running', '正在执行操作...', task_id),
    )
    try:
        clients, error = get_oci_clients(profile_config, validate=False)
        if error:
            raise Exception(error)
        compute_client, vnet_client = clients['compute'], clients['vnet']

        instance = compute_client.get_instance(instance_id).data
        instance_name = instance.display_name
        alias = profile_config.get('alias', '未知账户')

        action_map = {
            'START': ('START', 'RUNNING'),
            'STOP': ('STOP', 'STOPPED'),
            'RESTART': ('SOFTRESET', 'RUNNING'),
        }
        action_upper = action.upper()
        result_message = ''
        task_title = f'{action_upper} on {instance_name}'

        if action_upper in action_map:
            oci_action, target_state = action_map[action_upper]
            compute_client.instance_action(instance_id=instance_id, action=oci_action)
            db_execute('UPDATE tasks SET result=? WHERE id=?', (f'等待实例进入 {target_state} 状态...', task_id))
            oci.wait_until(
                compute_client,
                compute_client.get_instance(instance_id),
                'lifecycle_state',
                target_state,
                max_wait_seconds=300,
            )
            result_message = f'✅ 实例已成功 {action}!'
        elif action_upper == 'TERMINATE':
            compute_client.terminate_instance(
                instance_id,
                preserve_boot_volume=data.get('preserve_boot_volume', True),
            )
            db_execute('UPDATE tasks SET result=? WHERE id=?', ('等待实例进入 TERMINATED 状态...', task_id))
            oci.wait_until(
                compute_client,
                compute_client.get_instance(instance_id),
                'lifecycle_state',
                'TERMINATED',
                max_wait_seconds=300,
                succeed_on_not_found=True,
            )
            result_message = '✅ 实例已成功终止!'
        elif action_upper == 'CHANGEIP':
            vnic_id = data.get('vnic_id')
            if not vnic_id:
                raise Exception('缺少 vnic_id')
            private_ips = oci.pagination.list_call_get_all_results(
                vnet_client.list_private_ips,
                vnic_id=vnic_id,
            ).data
            primary_private_ip = next((p for p in private_ips if p.is_primary), None)
            if not primary_private_ip:
                raise Exception('未找到主私有IP')
            try:
                pub_ip_details = GetPublicIpByPrivateIpIdDetails(private_ip_id=primary_private_ip.id)
                existing_pub_ip = vnet_client.get_public_ip_by_private_ip_id(pub_ip_details).data
                if existing_pub_ip.lifetime == 'EPHEMERAL':
                    vnet_client.delete_public_ip(existing_pub_ip.id)
                    time.sleep(5)
            except ServiceError as e:
                if e.status != 404:
                    raise
            new_pub_ip = vnet_client.create_public_ip(
                CreatePublicIpDetails(
                    compartment_id=profile_config['tenancy'],
                    lifetime='EPHEMERAL',
                    private_ip_id=primary_private_ip.id,
                )
            ).data
            result_message = f'✅ 更换IP成功，新IP: {new_pub_ip.ip_address}'
            dns_update_msg = update_cloudflare_dns(instance_name, new_pub_ip.ip_address, 'A')
            result_message += f'\n{dns_update_msg}'
        elif action_upper == 'ASSIGNIPV6':
            vnic_id = data.get('vnic_id')
            if not vnic_id:
                raise Exception('缺少 vnic_id')

            enable_ipv6_networking(task_id, vnet_client, vnic_id, db_execute)

            db_execute('UPDATE tasks SET result=? WHERE id=?', ('正在检查现有 IPv6 地址...', task_id))
            existing_ipv6s = vnet_client.list_ipv6s(vnic_id=vnic_id).data

            if existing_ipv6s:
                ipv6_to_remove = [ip.id for ip in existing_ipv6s]
                db_execute(
                    'UPDATE tasks SET result=? WHERE id=?',
                    (f'检测到 {len(ipv6_to_remove)} 个旧 IPv6，正在删除以执行更换...', task_id),
                )
                logging.info(
                    f'Replacing IPv6 for instance {instance_name}: Deleting {len(ipv6_to_remove)} existing addresses.'
                )
                for ipv6_id in ipv6_to_remove:
                    try:
                        vnet_client.delete_ipv6(ipv6_id)
                    except Exception as e:
                        logging.warning(f'删除旧 IPv6 {ipv6_id} 失败: {e}')
                time.sleep(5)

            db_execute('UPDATE tasks SET result=? WHERE id=?', ('网络配置完成，正在为实例分配IPv6地址...', task_id))
            new_ipv6 = vnet_client.create_ipv6(CreateIpv6Details(vnic_id=vnic_id)).data
            result_message = f'✅ 已成功分配IPv6地址: {new_ipv6.ip_address}'
            dns_update_msg = update_cloudflare_dns(instance_name, new_ipv6.ip_address, 'AAAA')
            result_message += f'\n{dns_update_msg}'
        else:
            raise Exception(f'未知的操作: {action}')

        db_execute(
            'UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?',
            ('success', result_message, datetime.datetime.now(timezone.utc).isoformat(), task_id),
        )
        _notify_task_result(True, alias, task_title, result_message, data.get('_source'))
    except Exception as e:
        alias = profile_config.get('alias', '未知账户')
        task_title = f'{action.upper()} on instance'
        error_message = f'❌ 操作失败: {e}'
        db_execute(
            'UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?',
            ('failure', error_message, datetime.datetime.now(timezone.utc).isoformat(), task_id),
        )
        _notify_task_result(False, alias, task_title, str(e), data.get('_source'))


__all__ = ['run_instance_action_task']
