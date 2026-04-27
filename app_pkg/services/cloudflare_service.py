import logging

import requests

from app_pkg.repositories.integration_settings import load_cloudflare_config


def update_cloudflare_dns(subdomain, ip_address, record_type='A'):
    cf_config = load_cloudflare_config()
    api_token = cf_config.get('api_token')
    zone_id = cf_config.get('zone_id')
    domain = cf_config.get('domain')

    if not all([api_token, zone_id, domain]):
        logging.warning('Cloudflare 未配置，跳过 DNS 更新。')
        return 'Cloudflare 未配置，跳过 DNS 更新。'

    full_domain = f'{subdomain}.{domain}'
    api_url = f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records'
    headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json',
    }

    try:
        search_params = {'type': record_type, 'name': full_domain}
        response = requests.get(api_url, headers=headers, params=search_params, timeout=15)
        response.raise_for_status()
        search_result = response.json()

        dns_payload = {
            'type': record_type,
            'name': full_domain,
            'content': ip_address,
            'ttl': 60,
            'proxied': False,
        }

        if search_result['result']:
            record_id = search_result['result'][0]['id']
            update_url = f'{api_url}/{record_id}'
            response = requests.put(update_url, headers=headers, json=dns_payload, timeout=15)
            action_log = '更新'
        else:
            response = requests.post(api_url, headers=headers, json=dns_payload, timeout=15)
            action_log = '创建'

        response.raise_for_status()
        result_data = response.json()

        if result_data['success']:
            msg = f'✅ Cloudflare DNS 记录: {full_domain} -> {ip_address}'
            logging.info(f'成功 {action_log} Cloudflare DNS 记录: {full_domain} -> {ip_address}')
            return msg

        errors = result_data.get('errors', [{'message': '未知错误'}])
        error_msg = ', '.join([e['message'] for e in errors])
        msg = f'❌ {action_log} Cloudflare DNS 记录失败: {error_msg}'
        logging.error(msg)
        return msg
    except requests.RequestException as e:
        msg = f'❌ 更新 Cloudflare DNS 时发生网络错误: {e}'
        logging.error(msg)
        return msg
    except Exception as e:
        msg = f'❌ 更新 Cloudflare DNS 时发生未知错误: {e}'
        logging.error(msg)
        return msg
