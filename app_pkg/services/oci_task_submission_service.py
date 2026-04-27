import logging
import uuid

import oci

from app_pkg.repositories.integration_settings import load_default_script
from app_pkg.repositories.oci_profiles import load_profiles
from app_pkg.repositories.task_db import _create_task_entry
from app_pkg.services.oci_clients import get_oci_clients


class SubmissionError(Exception):
    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _get_profile_config(alias):
    profile_config = load_profiles().get('profiles', {}).get(alias)
    if not profile_config:
        raise SubmissionError(f"账号 '{alias}' 未找到", 404)
    return profile_config


def submit_instance_action(alias, data):
    action = data.get('action')
    instance_id = data.get('instance_id')
    if not action or not instance_id:
        raise SubmissionError('缺少 action 或 instance_id', 400)

    profile_config = _get_profile_config(alias)
    task_name = f"{action} on {data.get('instance_name', instance_id[-12:])}"
    task_id = _create_task_entry('action', task_name, alias)

    config_with_alias = profile_config.copy()
    config_with_alias['alias'] = alias

    task_payload = dict(data)
    task_payload['_source'] = 'web'

    from app_pkg.tasks.oci_tasks import _instance_action_task

    _instance_action_task.delay(task_id, config_with_alias, action, instance_id, task_payload)
    return {'message': f"'{action}' 请求已提交...", 'task_id': task_id}


def submit_launch_instance(alias, data):
    profile_config = _get_profile_config(alias)
    clients, error = get_oci_clients(profile_config, validate=False)
    if error:
        raise SubmissionError(error, 500)

    task_payload = dict(data or {})
    user_script = task_payload.get('startup_script', '').strip()
    if not user_script:
        server_default_script = load_default_script().strip()
        if server_default_script:
            logging.info('Using server-side default startup script.')
            task_payload['startup_script'] = server_default_script

    task_payload.setdefault('os_name_version', 'Canonical Ubuntu-22.04')

    display_name = task_payload.get('display_name_prefix', 'N/A')
    instance_count = int(task_payload.get('instance_count', 1) or 1)
    shape = task_payload.get('shape')
    auto_bind_domain = task_payload.get('auto_bind_domain', False)

    compute_client = clients['compute']
    compartment_id = profile_config['tenancy']

    try:
        all_instances = oci.pagination.list_call_get_all_results(
            compute_client.list_instances,
            compartment_id=compartment_id,
        ).data
        active_instances = [
            inst for inst in all_instances
            if inst.lifecycle_state not in ['TERMINATED', 'TERMINATING']
        ]

        if shape == 'VM.Standard.E2.1.Micro':
            existing_amd_count = sum(1 for inst in active_instances if inst.shape == shape)
            if (existing_amd_count + instance_count) > 2:
                raise SubmissionError(
                    f'免费账户最多只能创建2个AMD实例，您当前已有 {existing_amd_count} 个活动实例。',
                    400,
                )
    except SubmissionError:
        raise
    except Exception as e:
        logging.error(f'检查配额时发生严重错误: {e}')
        raise SubmissionError(f'检查配额时出错，请稍后重试: {e}', 500)

    from app_pkg.tasks.oci_tasks import _snatch_instance_task

    task_ids = []
    for i in range(instance_count):
        task_name = f'{display_name}-{i + 1}' if instance_count > 1 else display_name
        task_id = _create_task_entry('snatch', task_name, alias)

        per_task_payload = task_payload.copy()
        per_task_payload['display_name_prefix'] = task_name
        per_task_payload['auto_bind_domain'] = auto_bind_domain

        run_id = str(uuid.uuid4())
        _snatch_instance_task.delay(task_id, profile_config, alias, per_task_payload, run_id, auto_bind_domain)
        task_ids.append(task_id)

    return {
        'message': f'已提交 {instance_count} 个抢占实例任务...',
        'task_ids': task_ids,
    }


__all__ = ['SubmissionError', 'submit_instance_action', 'submit_launch_instance']
