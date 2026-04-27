import logging
import os
import uuid

import oci


def get_oci_clients(profile_config, validate=True):
    key_file_path = None
    try:
        config_for_sdk = profile_config.copy()
        proxy_url = None
        if 'proxy' in profile_config and profile_config['proxy']:
            proxy_url = profile_config['proxy']
            logging.info(f'Using proxy: {proxy_url} for OCI client.')

        if 'key_content' in profile_config:
            key_file_path = f'/tmp/{uuid.uuid4()}.pem'
            with open(key_file_path, 'w') as key_file:
                key_file.write(profile_config['key_content'])
            os.chmod(key_file_path, 0o600)
            config_for_sdk['key_file'] = key_file_path

        if validate:
            oci.config.validate_config(config_for_sdk)

        clients = {
            'identity': oci.identity.IdentityClient(config_for_sdk),
            'compute': oci.core.ComputeClient(config_for_sdk),
            'vnet': oci.core.VirtualNetworkClient(config_for_sdk),
            'bs': oci.core.BlockstorageClient(config_for_sdk),
        }

        if proxy_url:
            proxies = {'http': proxy_url, 'https': proxy_url}
            for client_obj in clients.values():
                if hasattr(client_obj, 'base_client') and hasattr(client_obj.base_client, 'session'):
                    client_obj.base_client.session.proxies = proxies

        return clients, None
    except Exception as e:
        return None, f'创建OCI客户端失败: {e}'
    finally:
        if key_file_path and os.path.exists(key_file_path):
            os.remove(key_file_path)
