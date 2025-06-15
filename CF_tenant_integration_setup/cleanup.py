import boto3
import sys
from botocore.exceptions import ClientError

cf = boto3.client('cloudformation')

def stack_exists(stack_name):
    try:
        cf.describe_stacks(StackName=stack_name)
        return True
    except ClientError as e:
        if "does not exist" in str(e):
            return False
        else:
            print(f"Error checking stack existence: {e}")
            sys.exit(1)

def delete_stack(stack_name):
    if stack_exists(stack_name):
        print(f"Deleting stack '{stack_name}'...")
        try:
            cf.delete_stack(StackName=stack_name)
            wait_for_stack_delete(stack_name)
        except ClientError as e:
            print(f"Failed to delete stack {stack_name}: {e}")
            sys.exit(1)
    else:
        print(f"Stack '{stack_name}' does not exist. Skipping...")

def wait_for_stack_delete(stack_name):
    print(f"Waiting for stack '{stack_name}' deletion to complete...")
    waiter = cf.get_waiter('stack_delete_complete')
    try:
        waiter.wait(StackName=stack_name)
        print(f"Stack '{stack_name}' deleted successfully.")
    except Exception as e:
        print(f"Error waiting for stack deletion: {e}")
        sys.exit(1)

def main():
    stacks_to_delete = [
        "SFTPStack",
        "ApiGatewayVpcEndpointStack",
        "ALBStack",
        "RouteTablesStack",
        "SubnetStack",
        "WAFStack",
        "Route53Stack",
        "IgwStack",
        "VgwStack",
        "SecurityGroupsStack",
        "VpcStack"
    ]

    for stack_name in stacks_to_delete:
        delete_stack(stack_name)

    print("All specified stacks have been deleted successfully.")

if __name__ == "__main__":
    main()
