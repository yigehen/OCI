import oci
from oci.exceptions import ServiceError


IDENTITY_DOMAINS_ERROR = "操作失败: 甲骨文已将您的租户迁移至新型 Identity Domains，传统 IAM 接口不兼容此操作。错误代码: {status}"


def _serialize_user(user):
    return {
        'id': user.id,
        'name': user.name,
        'description': user.description or '无',
        'email': user.email or '未绑定',
        'lifecycle_state': user.lifecycle_state,
        'time_created': user.time_created.isoformat() if user.time_created else '',
    }


def handle_identity_users_request(identity_client, tenancy_ocid, method, data=None):
    if method == 'GET':
        try:
            users = oci.pagination.list_call_get_all_results(
                identity_client.list_users,
                compartment_id=tenancy_ocid,
            ).data
            return [_serialize_user(user) for user in users], 200
        except ServiceError as e:
            return {'error': f'API 错误 ({e.status}): {e.message}'}, 500
        except Exception as e:
            return {'error': str(e)}, 500

    if method == 'POST':
        data = data or {}
        try:
            details = oci.identity.models.CreateUserDetails(
                compartment_id=tenancy_ocid,
                name=data.get('name'),
                description=data.get('description', 'Created via Web Panel'),
                email=data.get('email'),
            )
            new_user = identity_client.create_user(details).data
            return {
                'success': True,
                'message': f'用户 {new_user.name} 创建成功！',
                'user_id': new_user.id,
            }, 200
        except Exception as e:
            return {'error': f'创建用户失败: {e}'}, 500

    return {'error': '不支持的请求方法'}, 405


def handle_user_action_request(identity_client, user_id, action, data=None):
    data = data or {}
    try:
        if action == 'reset-password':
            res = identity_client.create_or_reset_ui_password(user_id).data
            return {
                'success': True,
                'message': '密码重置成功！请务必妥善保存生成的一次性密码。',
                'new_password': res.password,
            }, 200

        if action == 'clear-2fa':
            devices = oci.pagination.list_call_get_all_results(
                identity_client.list_mfa_totp_devices,
                user_id=user_id,
            ).data
            if not devices:
                return {'success': True, 'message': '该用户当前没有绑定任何 2FA 验证器。'}, 200
            for device in devices:
                identity_client.delete_mfa_totp_device(user_id=user_id, mfa_totp_device_id=device.id)
            return {
                'success': True,
                'message': f'成功清除了 {len(devices)} 个 2FA 绑定的设备！用户下次登录将无需验证码。',
            }, 200

        if action == 'update-email':
            new_email = data.get('email')
            if not new_email:
                return {'error': '新邮箱不能为空'}, 400
            details = oci.identity.models.UpdateUserDetails(email=new_email)
            identity_client.update_user(user_id, details)
            return {'success': True, 'message': f'邮箱已成功更新为: {new_email}'}, 200

        return {'error': '未知的操作指令'}, 400
    except ServiceError as e:
        if 'IdentityDomains' in str(e) or e.status == 404:
            return {'error': IDENTITY_DOMAINS_ERROR.format(status=e.status)}, 400
        return {'error': f'API 拒绝操作: {e.message}'}, 500
    except Exception as e:
        return {'error': f'执行失败: {e}'}, 500


__all__ = ['handle_identity_users_request', 'handle_user_action_request']
