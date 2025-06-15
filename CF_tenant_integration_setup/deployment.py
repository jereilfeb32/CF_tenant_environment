import boto3
import json
import os
import sys
from botocore.exceptions import ClientError

cf = boto3.client('cloudformation')
acm = boto3.client('acm')

def load_parameters(file_path):
    print(f"Loading parameters from: {file_path}")
    try:
        with open(file_path, 'r') as f:
            params_list = json.load(f)
        return {param['ParameterKey']: param['ParameterValue'] for param in params_list}
    except FileNotFoundError:
        print(f"Parameter file '{file_path}' not found. Skipping.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from '{file_path}': {e}")
        sys.exit(1)

def format_parameters(params_dict):
    formatted = []
    for k, v in params_dict.items():
        if v is None:
            print(f"Error: Parameter '{k}' is None.")
            sys.exit(1)
        if isinstance(v, list):
            v = ",".join(v)
        formatted.append({'ParameterKey': k, 'ParameterValue': str(v)})
    return formatted

def wait_for_stack(stack_name, action_type):
    print(f"Waiting for stack '{stack_name}' {action_type} to complete...")
    waiter = cf.get_waiter(f"stack_{action_type}_complete")
    try:
        waiter.wait(StackName=stack_name)
        print(f"Stack '{stack_name}' {action_type}d successfully.\n")
    except Exception as e:
        if 'No updates' in str(e):
            print(f"No updates needed for stack '{stack_name}'.\n")
        else:
            print(f"Error during stack {action_type}: {e}")
            print_stack_events(stack_name)
            sys.exit(1)

def stack_exists(stack_name):
    try:
        cf.describe_stacks(StackName=stack_name)
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ValidationError' and 'does not exist' in e.response['Error']['Message']:
            return False
        else:
            print(f"Error checking stack existence: {e}")
            sys.exit(1)

def deploy_stack(stack_name, template_body, parameters):
    params = format_parameters(parameters)
    if stack_exists(stack_name):
        print(f"Updating stack: {stack_name}")
        try:
            cf.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=params,
                Capabilities=['CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']
            )
            wait_for_stack(stack_name, 'update')
        except ClientError as e:
            if 'No updates are to be performed' in str(e):
                print(f"No update required for stack {stack_name}\n")
            else:
                print(f"Failed to update stack {stack_name}: {e}")
                print_stack_events(stack_name)
                sys.exit(1)
    else:
        print(f"Creating stack: {stack_name}")
        try:
            cf.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=params,
                Capabilities=['CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']
            )
            wait_for_stack(stack_name, 'create')
        except ClientError as e:
            print(f"Failed to create stack {stack_name}: {e}")
            print_stack_events(stack_name)
            sys.exit(1)

def get_stack_output(stack_name, output_key):
    try:
        outputs = cf.describe_stacks(StackName=stack_name)['Stacks'][0].get('Outputs', [])
        for output in outputs:
            if output['OutputKey'] == output_key:
                return output['OutputValue'].split(',') if ',' in output['OutputValue'] else output['OutputValue']
        print(f"Output key '{output_key}' not found in stack '{stack_name}'")
        return []
    except ClientError as e:
        print(f"Failed to get outputs for stack {stack_name}: {e}")
        return []

def read_template_file(file_path):
    try:
        with open(file_path, 'r') as file:
            content = file.read()
            if not content.strip():
                raise ValueError(f"Template file '{file_path}' is empty.")
            return content
    except Exception as e:
        print(f"Error reading template file '{file_path}': {e}")
        sys.exit(1)

def get_certificate_arn(project_name):
    try:
        certs = acm.list_certificates(CertificateStatuses=['ISSUED'])['CertificateSummaryList']
        for cert in certs:
            if project_name.lower() in cert['DomainName'].lower():
                return cert['CertificateArn']
        print(f"No matching ACM certificate found for project '{project_name}'.")
        sys.exit(1)
    except Exception as e:
        print(f"Error fetching ACM certificates: {e}")
        sys.exit(1)

def print_stack_events(stack_name):
    try:
        events = cf.describe_stack_events(StackName=stack_name)['StackEvents']
        print(f"Recent events for stack '{stack_name}':")
        for event in sorted(events, key=lambda e: e['Timestamp'], reverse=True)[:10]:
            status_reason = event.get('ResourceStatusReason', '')
            print(f"{event['Timestamp']} {event['ResourceStatus']} {event['ResourceType']} {event['LogicalResourceId']} {status_reason}")
    except Exception as e:
        print(f"Could not retrieve stack events for debugging: {e}")

def join_list_to_string(value):
    return ",".join(value) if isinstance(value, list) else value

def main():
    base_path = os.path.join(".", "templates")
    param_path = os.path.join(".", "parameters")

    base_params = load_parameters(os.path.join(param_path, "parameters.json"))
    print("Loaded parameters.\n")
    print("Base parameters after loading:", base_params)
    print("Keys in base_params:", base_params.keys())

    required_keys = ["ProjectName", "VpcCidr", "DomainName", "AvailabilityZones", "ACMCertificateArn"]
    for key in required_keys:
        if key not in base_params or base_params[key] in [None, ""]:
            if key == "ACMCertificateArn":
                base_params["ACMCertificateArn"] = get_certificate_arn(base_params.get("ProjectName", ""))
            else:
                print(f"Required parameter '{key}' is missing.")
                sys.exit(1)

    list_keys_to_check = [
        "AvailabilityZones", "PublicSubnetCidrs", "PrivateSubnetCidrs",
        "ALBSubnetCidrs", "GWLBSubnetCidrs", "SFTPSubnetCidrs"
    ]
    for key in list_keys_to_check:
        if key in base_params:
            items = base_params[key].split(",")
            if len(items) < 3:
                print(f"Each subnet CIDR list and AZ list must contain at least 3 entries for '{key}'.")
                sys.exit(1)

    deploy_stack("VpcStack", read_template_file(os.path.join(base_path, "vpc.yaml")), {
        "ProjectName": base_params["ProjectName"],
        "VpcCidr": base_params["VpcCidr"]
    })
    vpc_id = get_stack_output("VpcStack", "VpcId")

    base_params["VpcId"] = vpc_id

    deploy_stack("IgwStack", read_template_file(os.path.join(base_path, "igw.yaml")), {
        "ProjectName": base_params["ProjectName"],
        "VpcId": vpc_id
    })
    igw_id = get_stack_output("IgwStack", "InternetGatewayId")

    deploy_stack("VgwStack", read_template_file(os.path.join(base_path, "vgw.yaml")), {
        "ProjectName": base_params["ProjectName"],
        "VpcId": vpc_id
    })
    vgw_id = get_stack_output("VgwStack", "VpnGatewayId")

    subnets_template = read_template_file(os.path.join(base_path, "subnets.yaml"))
    subnet_parameters = {
        "ProjectName": base_params["ProjectName"],
        "AvailabilityZones": join_list_to_string(base_params["AvailabilityZones"]),
        "PublicSubnetCidrs": join_list_to_string(base_params["PublicSubnetCidrs"]),
        "PrivateSubnetCidrs": join_list_to_string(base_params["PrivateSubnetCidrs"]),
        "ALBSubnetCidrs": join_list_to_string(base_params["ALBSubnetCidrs"]),
        "GWLBSubnetCidrs": join_list_to_string(base_params["GWLBSubnetCidrs"]),
        "SFTPSubnetCidrs": join_list_to_string(base_params["SFTPSubnetCidrs"]),
        "VpcId": base_params["VpcId"]
    }

    print("Subnet parameters before deployment:", subnet_parameters)

    deploy_stack("SubnetStack", subnets_template, subnet_parameters)

    public_subnet_ids = get_stack_output("SubnetStack", "PublicSubnetIds")
    private_subnet_ids = get_stack_output("SubnetStack", "PrivateSubnetIds")
    alb_subnet_ids = get_stack_output("SubnetStack", "ALBSubnetIds")
    gwlb_subnet_ids = get_stack_output("SubnetStack", "GWLBSubnetIds")
    sftp_subnet_ids = get_stack_output("SubnetStack", "SFTPSubnetIds")

    deploy_stack("SecurityGroupsStack", read_template_file(os.path.join(base_path, "security-groups.yaml")), {
        "ProjectName": base_params["ProjectName"],
        "VpcId": vpc_id
    })

    alb_sg_id = get_stack_output("SecurityGroupsStack", "ALBSecurityGroupId")
    tgtgrp_sg_id = get_stack_output("SecurityGroupsStack", "TargetGroupSecurityGroupId")
    gwlb_sg_id = get_stack_output("SecurityGroupsStack", "GWLBSecurityGroupId")
    sftp_sg_id = get_stack_output("SecurityGroupsStack", "SFTPSecurityGroupId")

    deploy_stack("RouteTablesStack", read_template_file(os.path.join(base_path, "route-tables.yaml")), {
        "ProjectName": base_params["ProjectName"],
        "VpcId": vpc_id,
        "InternetGatewayId": igw_id,
        "PublicSubnetIds": join_list_to_string(public_subnet_ids),
        "PrivateSubnetIds": join_list_to_string(private_subnet_ids),
        "ALBSubnetIds": join_list_to_string(alb_subnet_ids),
        "GWLBSubnetIds": join_list_to_string(gwlb_subnet_ids),
        "SFTPSubnetIds": join_list_to_string(sftp_subnet_ids),
    })

    deploy_stack("Route53Stack", read_template_file(os.path.join(base_path, "route53-private-hosted-zone.yaml")), {
        "ProjectName": base_params["ProjectName"],
        "VpcId": vpc_id,
        "DomainName": base_params["DomainName"]
    })

    deploy_stack("WAFStack", read_template_file(os.path.join(base_path, "waf.yaml")), {
        "ProjectName": base_params["ProjectName"]
    })
    waf_arn = get_stack_output("WAFStack", "WebACLArn")

    deploy_stack("ALBStack", read_template_file(os.path.join(base_path, "alb.yaml")), {
        "ProjectName": base_params["ProjectName"],
        "ALBSubnetIds": join_list_to_string(alb_subnet_ids),
        "ALBSecurityGroupId": alb_sg_id,
        "TargetGroupSecurityGroupId": tgtgrp_sg_id,
        "ACMCertificateArn": base_params["ACMCertificateArn"],
        "WAFWebACLArn": waf_arn,
        "VpcId": vpc_id
    })

    deploy_stack("SFTPStack", read_template_file(os.path.join(base_path, "sftp-endpoint.yaml")), {
        "ProjectName": base_params["ProjectName"],
        "VpcId": vpc_id,
        "SubnetIds": join_list_to_string(sftp_subnet_ids),
        "SecurityGroupIds": join_list_to_string(sftp_sg_id)
    })

    print("\nAll stacks deployed successfully.")

if __name__ == "__main__":
    main()

