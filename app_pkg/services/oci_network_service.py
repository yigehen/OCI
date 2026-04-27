import base64
import json
import logging
import random

import oci
from oci.core.models import (
    AddVcnIpv6CidrDetails,
    CreateInternetGatewayDetails,
    CreateSubnetDetails,
    CreateVcnDetails,
    EgressSecurityRule,
    IngressSecurityRule,
    RouteRule,
    UpdateRouteTableDetails,
    UpdateSecurityListDetails,
    UpdateSubnetDetails,
)
from oci.exceptions import ServiceError


def ensure_subnet_in_profile(task_id, alias, vnet_client, tenancy_ocid, load_profiles, save_profiles, db_execute):
    all_data = load_profiles()
    profiles = all_data.get('profiles', {})
    profile_config = profiles.get(alias, {})
    subnet_id = profile_config.get('default_subnet_ocid')
    if subnet_id:
        try:
            if vnet_client.get_subnet(subnet_id).data.lifecycle_state == 'AVAILABLE':
                return subnet_id
        except ServiceError as e:
            if e.status != 404:
                raise
            logging.warning(f'Saved subnet {subnet_id} not found, will auto-discover or create a new one.')
    try:
        vcns = vnet_client.list_vcns(compartment_id=tenancy_ocid).data
        if vcns:
            default_vcn = vcns[0]
            subnets = vnet_client.list_subnets(compartment_id=tenancy_ocid, vcn_id=default_vcn.id).data
            if subnets:
                default_subnet = subnets[0]
                all_data['profiles'][alias]['default_subnet_ocid'] = default_subnet.id
                save_profiles(all_data)
                return default_subnet.id
    except Exception as e:
        logging.error(f'An error occurred during auto-discovery: {e}. Falling back to creation.')
    if task_id:
        db_execute('UPDATE tasks SET result=? WHERE id=?', ('首次运行，正在自动创建网络资源 (VCN, 子网等)，预计需要2-3分钟...', task_id))
    vcn_name = f'vcn-autocreated-{alias}-{random.randint(100, 999)}'
    vcn_details = CreateVcnDetails(cidr_block='10.0.0.0/16', display_name=vcn_name, compartment_id=tenancy_ocid)
    vcn = vnet_client.create_vcn(vcn_details).data
    if task_id:
        db_execute('UPDATE tasks SET result=? WHERE id=?', ('(1/3) VCN 已创建，正在等待其生效...', task_id))
    oci.wait_until(vnet_client, vnet_client.get_vcn(vcn.id), 'lifecycle_state', 'AVAILABLE')
    ig_name = f'ig-autocreated-{alias}-{random.randint(100, 999)}'
    ig_details = CreateInternetGatewayDetails(display_name=ig_name, compartment_id=tenancy_ocid, is_enabled=True, vcn_id=vcn.id)
    ig = vnet_client.create_internet_gateway(ig_details).data
    if task_id:
        db_execute('UPDATE tasks SET result=? WHERE id=?', ('(2/3) 互联网网关已创建并添加路由...', task_id))
    oci.wait_until(vnet_client, vnet_client.get_internet_gateway(ig.id), 'lifecycle_state', 'AVAILABLE')
    route_table_id = vcn.default_route_table_id
    rt_rules = vnet_client.get_route_table(route_table_id).data.route_rules
    rt_rules.append(RouteRule(destination='0.0.0.0/0', network_entity_id=ig.id))
    vnet_client.update_route_table(route_table_id, UpdateRouteTableDetails(route_rules=rt_rules))
    subnet_name = f'subnet-autocreated-{alias}-{random.randint(100, 999)}'
    subnet_details = CreateSubnetDetails(compartment_id=tenancy_ocid, vcn_id=vcn.id, cidr_block='10.0.1.0/24', display_name=subnet_name)
    subnet = vnet_client.create_subnet(subnet_details).data
    if task_id:
        db_execute('UPDATE tasks SET result=? WHERE id=?', ('(3/3) 子网已创建，网络设置完成！', task_id))
    oci.wait_until(vnet_client, vnet_client.get_subnet(subnet.id), 'lifecycle_state', 'AVAILABLE')
    all_data['profiles'][alias]['default_subnet_ocid'] = subnet.id
    save_profiles(all_data)
    return subnet.id


def get_user_data(password=None, startup_script=None, enable_password_auth=False):
    default_script = """
echo \"=== [Network Fix] Forcing IPv4 for GitHub to prevent Oracle IPv6 hang ===\"
echo \"140.82.113.3 github.com\" >> /etc/hosts
echo \"185.199.108.133 raw.githubusercontent.com\" >> /etc/hosts
echo 'Acquire::ForceIPv4 \"true\";' > /etc/apt/apt.conf.d/99force-ipv4
alias wget='wget -4'

echo \"Waiting for apt lock to be released...\"
while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do
   echo \"Another apt/dpkg process is running. Waiting 10 seconds...\"
   sleep 10
done

echo \"Starting package installation with retries...\"
for i in 1 2 3; do
  apt-get update && apt-get install -y curl wget unzip git socat cron && break
  echo \"APT commands failed (attempt $i/3), retrying in 15 seconds...\"
  sleep 15
done
"""
    script_parts = ['#cloud-config']
    if enable_password_auth and password:
        script_parts.extend(['chpasswd:', '  expire: False', '  list:', f'    - root:{password}'])
    script_parts.append('runcmd:')
    if enable_password_auth:
        script_parts.append("  - \"sed -i -e '/^#*PasswordAuthentication/s/^.*$/PasswordAuthentication yes/' /etc/ssh/sshd_config\"")
        script_parts.append("  - \"sed -i -e '/^#*PermitRootLogin/s/^.*$/PermitRootLogin yes/' /etc/ssh/sshd_config\"")
    else:
        script_parts.append("  - \"sed -i -e '/^#*PasswordAuthentication/s/^.*$/PasswordAuthentication no/' /etc/ssh/sshd_config\"")
        script_parts.append("  - \"sed -i -e '/^#*PermitRootLogin/s/^.*$/PermitRootLogin yes/' /etc/ssh/sshd_config\"")
    script_parts.append("  - 'rm -f /etc/ssh/sshd_config.d/60-cloudimg-settings.conf'")
    script_parts.append("  - 'mkdir -p /root/.ssh && cp /home/ubuntu/.ssh/authorized_keys /root/.ssh/authorized_keys && chown root:root /root/.ssh/authorized_keys'")
    script_parts.append(f"  - [ bash, -c, {json.dumps(default_script)} ]")
    if startup_script and startup_script.strip():
        script_parts.append(f"  - [ bash, -c, {json.dumps(startup_script.strip())} ]")
    script_parts.append('  - systemctl restart sshd || service sshd restart || service ssh restart')
    script = '\n'.join(script_parts)
    return base64.b64encode(script.encode('utf-8')).decode('utf-8')


def enable_ipv6_networking(task_id, vnet_client, vnic_id, db_execute):
    db_execute('UPDATE tasks SET result=? WHERE id=?', ('(1/5) 正在获取网络资源...', task_id))
    vnic = vnet_client.get_vnic(vnic_id).data
    subnet = vnet_client.get_subnet(vnic.subnet_id).data
    vcn = vnet_client.get_vcn(subnet.vcn_id).data
    if not vcn.ipv6_cidr_blocks:
        db_execute('UPDATE tasks SET result=? WHERE id=?', ('(2/5) 正在为VCN开启IPv6...', task_id))
        details = AddVcnIpv6CidrDetails(is_oracle_gua_allocation_enabled=True)
        vnet_client.add_ipv6_vcn_cidr(vcn_id=vcn.id, add_vcn_ipv6_cidr_details=details)
        oci.wait_until(vnet_client, vnet_client.get_vcn(vcn.id), 'lifecycle_state', 'AVAILABLE', max_wait_seconds=300)
        vcn = vnet_client.get_vcn(vcn.id).data
        logging.info(f'VCN {vcn.id} 已成功开启IPv6，地址段: {vcn.ipv6_cidr_blocks}')
    if not subnet.ipv6_cidr_block:
        db_execute('UPDATE tasks SET result=? WHERE id=?', ('(3/5) 正在为子网分配IPv6地址段...', task_id))
        vcn_ipv6_cidr = vcn.ipv6_cidr_blocks[0]
        subnet_ipv6_cidr = vcn_ipv6_cidr.replace('/56', '/64')
        details = UpdateSubnetDetails(ipv6_cidr_block=subnet_ipv6_cidr)
        vnet_client.update_subnet(subnet.id, details)
        oci.wait_until(vnet_client, vnet_client.get_subnet(subnet.id), 'lifecycle_state', 'AVAILABLE', max_wait_seconds=300)
        logging.info(f'Subnet {subnet.id} 已成功分配IPv6地址段: {subnet_ipv6_cidr}')
    db_execute('UPDATE tasks SET result=? WHERE id=?', ('(4/5) 正在更新路由表以支持IPv6...', task_id))
    route_table = vnet_client.get_route_table(vcn.default_route_table_id).data
    igws = vnet_client.list_internet_gateways(compartment_id=vcn.compartment_id, vcn_id=vcn.id).data
    if not igws:
        raise Exception('未找到互联网网关，无法为IPv6添加路由规则。')
    igw_id = igws[0].id
    ipv6_route_exists = any(rule.destination == '::/0' for rule in route_table.route_rules)
    if not ipv6_route_exists:
        new_rules = list(route_table.route_rules)
        new_rules.append(RouteRule(destination='::/0', network_entity_id=igw_id))
        vnet_client.update_route_table(route_table.id, UpdateRouteTableDetails(route_rules=new_rules))
        logging.info(f'已为路由表 {route_table.id} 添加IPv6默认路由。')
    db_execute('UPDATE tasks SET result=? WHERE id=?', ('(5/5) 正在更新安全规则(入站/出站)以支持IPv6...', task_id))
    security_list = vnet_client.get_security_list(vcn.default_security_list_id).data
    current_egress = list(security_list.egress_security_rules)
    current_ingress = list(security_list.ingress_security_rules)
    has_changes = False
    if not any(rule.destination == '::/0' for rule in current_egress):
        current_egress.append(EgressSecurityRule(destination='::/0', protocol='all', is_stateless=False, destination_type='CIDR_BLOCK'))
        has_changes = True
        logging.info('准备添加 IPv6 出站规则')
    if not any(rule.source == '::/0' for rule in current_ingress):
        current_ingress.append(IngressSecurityRule(source='::/0', protocol='all', is_stateless=False, source_type='CIDR_BLOCK'))
        has_changes = True
        logging.info('准备添加 IPv6 入站规则')
    if has_changes:
        update_details = UpdateSecurityListDetails(egress_security_rules=current_egress, ingress_security_rules=current_ingress)
        vnet_client.update_security_list(security_list.id, update_details)
        logging.info(f'已成功为安全列表 {security_list.id} 更新 IPv6 规则。')
    else:
        logging.info('IPv6 安全规则已存在，无需更新。')
