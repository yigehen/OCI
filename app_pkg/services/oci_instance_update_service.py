import datetime
import time
from datetime import timezone

import oci
from oci.core.models import UpdateBootVolumeDetails, UpdateInstanceDetails, UpdateInstanceShapeConfigDetails

from app_pkg.services.oci_clients import get_oci_clients


def run_update_instance_details_task(task_id, profile_config, data, db_execute):
    db_execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?', ('running', '正在更新实例...', task_id))
    try:
        clients, error = get_oci_clients(profile_config, validate=False)
        if error:
            raise Exception(error)

        compute_client = clients['compute']
        bs_client = clients['bs']
        action = data.get('action')
        instance_id = data.get('instance_id')
        instance = compute_client.get_instance(instance_id).data

        if action == 'update_display_name':
            details = UpdateInstanceDetails(display_name=data.get('display_name'))
            compute_client.update_instance(instance_id, details)
            result_message = '✅ 实例名称更新成功!'
        elif action == 'update_shape':
            if instance.lifecycle_state != 'STOPPED':
                raise Exception('必须先停止实例才能修改CPU和内存。')
            shape_config = UpdateInstanceShapeConfigDetails(
                ocpus=data.get('ocpus'),
                memory_in_gbs=data.get('memory_in_gbs'),
            )
            details = UpdateInstanceDetails(shape_config=shape_config)
            compute_client.update_instance(instance_id, details)
            result_message = '✅ CPU/内存配置更新成功！请手动启动实例。'
        elif action == 'update_boot_volume':
            boot_vol_attachments = oci.pagination.list_call_get_all_results(
                compute_client.list_boot_volume_attachments,
                instance.availability_domain,
                profile_config['tenancy'],
                instance_id=instance_id,
            ).data
            if not boot_vol_attachments:
                raise Exception('找不到引导卷')

            boot_volume_id = boot_vol_attachments[0].boot_volume_id
            current_boot_volume = bs_client.get_boot_volume(boot_volume_id).data
            current_size = int(current_boot_volume.size_in_gbs)
            current_vpus = int(current_boot_volume.vpus_per_gb)

            update_data = {}
            if data.get('size_in_gbs') is not None:
                requested_size = int(data.get('size_in_gbs'))
                if requested_size < current_size:
                    raise Exception(
                        f'OCI 引导卷不支持缩容：当前 {current_size} GB，目标 {requested_size} GB。若必须变小，请手动备份/重建实例，本程序不会自动终止实例。'
                    )
                if requested_size == current_size:
                    raise Exception(f'引导卷大小未变化：当前已经是 {current_size} GB。')
                update_data['size_in_gbs'] = requested_size

            if data.get('vpus_per_gb') is not None:
                requested_vpus = int(data.get('vpus_per_gb'))
                if requested_vpus != current_vpus:
                    update_data['vpus_per_gb'] = requested_vpus

            if not update_data:
                raise Exception('没有提供任何有效的引导卷更新信息。')

            target_size = update_data.get('size_in_gbs', current_size)
            target_vpus = update_data.get('vpus_per_gb', current_vpus)
            db_execute(
                'UPDATE tasks SET result = ? WHERE id = ?',
                (
                    f'正在提交引导卷更新请求... 当前: {current_size} GB/{current_vpus} VPU，目标: {target_size} GB/{target_vpus} VPU',
                    task_id,
                ),
            )

            details = UpdateBootVolumeDetails(**update_data)
            response = bs_client.update_boot_volume(boot_volume_id, details)

            work_request_id = None
            try:
                if response and getattr(response, 'headers', None):
                    work_request_id = response.headers.get('opc-work-request-id')
            except Exception:
                pass

            if work_request_id:
                db_execute(
                    'UPDATE tasks SET result = ? WHERE id = ?',
                    (
                        f'引导卷更新请求已提交，正在等待 OCI 后台任务完成... Work Request: {work_request_id}',
                        task_id,
                    ),
                )
            else:
                db_execute(
                    'UPDATE tasks SET result = ? WHERE id = ?',
                    ('引导卷更新请求已提交，正在轮询 OCI 引导卷最新状态...', task_id),
                )

            max_wait_seconds = 600
            poll_interval = 5
            start_ts = time.time()
            resize_confirmed = False

            while time.time() - start_ts < max_wait_seconds:
                latest_boot_volume = bs_client.get_boot_volume(boot_volume_id).data
                latest_size = int(latest_boot_volume.size_in_gbs)
                latest_vpus = int(latest_boot_volume.vpus_per_gb)
                latest_state = getattr(latest_boot_volume, 'lifecycle_state', 'UNKNOWN')

                if latest_size == target_size and latest_vpus == target_vpus and latest_state in ['AVAILABLE', 'PROVISIONING', 'RESTORING']:
                    resize_confirmed = True
                    break

                elapsed = int(time.time() - start_ts)
                db_execute(
                    'UPDATE tasks SET result = ? WHERE id = ?',
                    (
                        f'正在等待引导卷变更生效... 已等待 {elapsed}s，当前: {latest_size} GB/{latest_vpus} VPU，状态: {latest_state}，目标: {target_size} GB/{target_vpus} VPU',
                        task_id,
                    ),
                )
                time.sleep(poll_interval)

            if not resize_confirmed:
                latest_boot_volume = bs_client.get_boot_volume(boot_volume_id).data
                latest_size = int(latest_boot_volume.size_in_gbs)
                latest_vpus = int(latest_boot_volume.vpus_per_gb)
                latest_state = getattr(latest_boot_volume, 'lifecycle_state', 'UNKNOWN')
                raise Exception(
                    f'等待 OCI 引导卷更新超时。当前: {latest_size} GB/{latest_vpus} VPU，状态: {latest_state}；目标: {target_size} GB/{target_vpus} VPU'
                )

            tips = []
            if 'size_in_gbs' in update_data:
                tips.append('云盘容量已确认更新；如果实例系统内 df -h 仍未变大，请手动扩展分区/文件系统')
            if work_request_id:
                tips.append(f'Work Request: {work_request_id}')
            result_message = '✅ 引导卷更新成功！' + (f"（{'；'.join(tips)}）" if tips else '')
        else:
            raise Exception(f'未知的更新操作: {action}')

        db_execute(
            'UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?',
            ('success', result_message, datetime.datetime.now(timezone.utc).isoformat(), task_id),
        )
    except Exception as e:
        db_execute(
            'UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?',
            ('failure', f'❌ 操作失败: {e}', datetime.datetime.now(timezone.utc).isoformat(), task_id),
        )


__all__ = ['run_update_instance_details_task']
