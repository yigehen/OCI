from app_pkg.extensions import celery
from app_pkg.repositories.task_db import _db_execute_celery
from app_pkg.services.oci_instance_action_service import run_instance_action_task
from app_pkg.services.oci_instance_update_service import run_update_instance_details_task
from app_pkg.services.oci_snatch_service import run_snatch_instance_task
from blueprints.oci_panel import (
    recover_snatching_tasks,
    init_db,
)


@celery.task
def _instance_action_task(task_id, profile_config, action, instance_id, data):
    return run_instance_action_task(task_id, profile_config, action, instance_id, data, _db_execute_celery)


@celery.task
def _snatch_instance_task(task_id, profile_config, alias, details, run_id, auto_bind_domain=False):
    return run_snatch_instance_task(task_id, profile_config, alias, details, run_id, auto_bind_domain, _db_execute_celery)


@celery.task
def _update_instance_details_task(task_id, profile_config, data):
    return run_update_instance_details_task(task_id, profile_config, data, _db_execute_celery)


__all__ = [
    'recover_snatching_tasks',
    'init_db',
    '_instance_action_task',
    '_snatch_instance_task',
    '_update_instance_details_task',
]
