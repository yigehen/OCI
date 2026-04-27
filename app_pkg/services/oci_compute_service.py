import logging

import oci
from oci.core.models import GetPublicIpByPrivateIpIdDetails
from oci.exceptions import ServiceError


def list_instance_details(profile_config, clients):
    compute_client = clients['compute']
    vnet_client = clients['vnet']
    bs_client = clients['bs']
    compartment_id = profile_config['tenancy']

    instances = oci.pagination.list_call_get_all_results(
        compute_client.list_instances,
        compartment_id=compartment_id,
    ).data
    instance_details_list = []

    for instance in instances:
        data = {
            'display_name': instance.display_name,
            'id': instance.id,
            'lifecycle_state': instance.lifecycle_state,
            'shape': instance.shape,
            'time_created': instance.time_created.isoformat() if instance.time_created else None,
            'ocpus': getattr(instance.shape_config, 'ocpus', 'N/A'),
            'memory_in_gbs': getattr(instance.shape_config, 'memory_in_gbs', 'N/A'),
            'public_ip': '无',
            'ipv6_address': '无',
            'boot_volume_size_gb': 'N/A',
            'vnic_id': None,
            'subnet_id': None,
        }
        try:
            if instance.lifecycle_state not in ['TERMINATED', 'TERMINATING']:
                vnic_attachments = oci.pagination.list_call_get_all_results(
                    compute_client.list_vnic_attachments,
                    compartment_id=compartment_id,
                    instance_id=instance.id,
                ).data
                if vnic_attachments:
                    vnic_id = vnic_attachments[0].vnic_id
                    data.update({'vnic_id': vnic_id, 'subnet_id': vnic_attachments[0].subnet_id})

                    vnic = vnet_client.get_vnic(vnic_id).data
                    ipv4_display_list = []
                    private_ips = oci.pagination.list_call_get_all_results(
                        vnet_client.list_private_ips,
                        vnic_id=vnic_id,
                    ).data
                    private_ips.sort(key=lambda x: not x.is_primary)

                    for pip in private_ips:
                        pub_ip_str = None
                        if pip.is_primary:
                            pub_ip_str = vnic.public_ip
                        else:
                            try:
                                pub_ip_obj = vnet_client.get_public_ip_by_private_ip_id(
                                    GetPublicIpByPrivateIpIdDetails(private_ip_id=pip.id)
                                ).data
                                pub_ip_str = pub_ip_obj.ip_address
                            except Exception:
                                pass
                        if pub_ip_str:
                            ipv4_display_list.append(pub_ip_str)

                    if ipv4_display_list:
                        data['public_ip'] = '<br>'.join(ipv4_display_list)

                    ipv6s = vnet_client.list_ipv6s(vnic_id=vnic_id).data
                    if ipv6s:
                        data['ipv6_address'] = '<br>'.join([ip.ip_address for ip in ipv6s])

                boot_vol_attachments = oci.pagination.list_call_get_all_results(
                    compute_client.list_boot_volume_attachments,
                    instance.availability_domain,
                    compartment_id,
                    instance_id=instance.id,
                ).data
                if boot_vol_attachments:
                    boot_vol = bs_client.get_boot_volume(boot_vol_attachments[0].boot_volume_id).data
                    data['boot_volume_size_gb'] = f"{int(boot_vol.size_in_gbs)} GB"
        except ServiceError as se:
            if se.status == 404:
                logging.warning(f'Could not fetch details for instance {instance.display_name} ({instance.id}), it might have been terminated.')
            else:
                logging.error(f'OCI ServiceError for instance {instance.display_name}: {se}')
        except Exception as ex:
            logging.error(f'Generic exception while fetching details for instance {instance.display_name}: {ex}')
        instance_details_list.append(data)

    return instance_details_list


def get_instance_detail_payload(instance_id, profile_config, clients):
    compute_client = clients['compute']
    bs_client = clients['bs']
    vnet_client = clients['vnet']
    compartment_id = profile_config['tenancy']

    instance = compute_client.get_instance(instance_id).data
    boot_vol_attachments = oci.pagination.list_call_get_all_results(
        compute_client.list_boot_volume_attachments,
        instance.availability_domain,
        compartment_id,
        instance_id=instance.id,
    ).data

    boot_vol_size = 0
    vpus = 10
    boot_volume_id = None

    if boot_vol_attachments:
        boot_volume_id = boot_vol_attachments[0].boot_volume_id
        boot_volume = bs_client.get_boot_volume(boot_volume_id).data
        boot_vol_size = int(boot_volume.size_in_gbs)
        vpus = int(boot_volume.vpus_per_gb)

    ip_list = []
    ipv6_list = []

    try:
        vnic_attachments = oci.pagination.list_call_get_all_results(
            compute_client.list_vnic_attachments,
            compartment_id=compartment_id,
            instance_id=instance.id,
        ).data
        if vnic_attachments:
            vnic_id = vnic_attachments[0].vnic_id
            private_ips = oci.pagination.list_call_get_all_results(
                vnet_client.list_private_ips,
                vnic_id=vnic_id,
            ).data
            for pip in private_ips:
                pub_ip_val = '无'
                if pip.is_primary:
                    try:
                        vnic_info = vnet_client.get_vnic(vnic_id).data
                        if vnic_info.public_ip:
                            pub_ip_val = vnic_info.public_ip
                    except Exception:
                        pass
                else:
                    try:
                        pub_ip_obj = vnet_client.get_public_ip_by_private_ip_id(
                            GetPublicIpByPrivateIpIdDetails(private_ip_id=pip.id)
                        ).data
                        pub_ip_val = pub_ip_obj.ip_address
                    except Exception:
                        pass

                ip_list.append({
                    'private_ip': pip.ip_address,
                    'public_ip': pub_ip_val,
                    'is_primary': pip.is_primary,
                    'id': pip.id,
                })

            ipv6s = oci.pagination.list_call_get_all_results(vnet_client.list_ipv6s, vnic_id=vnic_id).data
            for ip in ipv6s:
                ipv6_list.append({'id': ip.id, 'ip_address': ip.ip_address})
    except Exception as e:
        logging.error(f'Error fetching IPs for instance details: {e}')

    return {
        'display_name': instance.display_name,
        'shape': instance.shape,
        'ocpus': instance.shape_config.ocpus,
        'memory_in_gbs': instance.shape_config.memory_in_gbs,
        'boot_volume_id': boot_volume_id,
        'boot_volume_size_in_gbs': boot_vol_size,
        'vpus_per_gb': vpus,
        'ips': ip_list,
        'ipv6s': ipv6_list,
    }


__all__ = ['list_instance_details', 'get_instance_detail_payload']
