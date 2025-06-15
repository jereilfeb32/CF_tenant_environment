import boto3
import sys

def add_vpc_endpoint_service_permission(region, target_account, service_name):
    ec2 = boto3.client('ec2', region_name=region)

    print(f"Retrieving VPC Endpoint services in region {region}...")
    response = ec2.describe_vpc_endpoint_services()
    services = response.get('ServiceDetails', [])

    service = next((s for s in services if s['ServiceName'] == service_name), None)
    if not service:
        print(f"Service {service_name} not found.")
        sys.exit(1)

    service_id = service['ServiceId']
    print(f"Found Service ID: {service_id}")

    principal_arn = f"arn:aws:iam::{target_account}:root"
    print(f"Adding permission for account {target_account} to access service {service_name}...")

    try:
        modify_response = ec2.modify_vpc_endpoint_service_permissions(
            ServiceId=service_id,
            AddAllowedPrincipals=[principal_arn]
        )
        if modify_response.get('ReturnValue', False):
            print(f"Successfully added permission for account {target_account}.")
        else:
            print(f"Failed to add permission for account {target_account}.")
    except Exception as e:
        print(f"Error adding permission: {e}")
        sys.exit(1)

if __name__ == "__main__":
    region = "ap-southeast-1"
    target_account = "975050199901"
    service_name = "com.amazonaws.vpce.ap-southeast-1.vpce-svc-03b139aa082f90800"

    add_vpc_endpoint_service_permission(region, target_account, service_name)
