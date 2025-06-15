import boto3
import json
import os
import time
import sys
from botocore.exceptions import ClientError

# ---------------------------
# AWS CLIENT
# ---------------------------
cf = boto3.client('cloudformation')

# ---------------------------
# STACKS TO DEPLOY
# ---------------------------
STACKS = [
    {
        "name": "egressVPCStack",
        "template": os.path.join("templates", "vpc.yaml"),
        "parameters": os.path.join("parameters", "vpc-parameters.json"),
    },
    {
        "name": "gwlbeVPCStack",
        "template": os.path.join("templates", "gwlbe-endpoint.yaml"),
        "parameters": os.path.join("parameters", "gwlbe-parameters.json"),
    },
    {
        "name": "gwlbeRouteStack",
        "template": os.path.join("templates", "gwlbe-routes.yaml"),
        "parameters": os.path.join("parameters", "gwlbe-routes-parameters.json"),
    },
    {
        "name": "egressNGWStack",
        "template": os.path.join("templates", "ngw.yaml"),
        "parameters": os.path.join("parameters", "ngw-parameters.json"),
    },
]

# ---------------------------
# HELPERS
# ---------------------------
def load_template_body(template_path):
    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")
    with open(template_path, 'r') as f:
        return f.read()

def load_parameters(params_path):
    if not os.path.isfile(params_path):
        raise FileNotFoundError(f"Parameter file not found: {params_path}")
    with open(params_path, 'r') as f:
        data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Parameter file must contain a JSON array: {params_path}")
        return data

def deploy_stack(stack_name, template_path, parameters_path):
    print(f"\n[START] Deploying stack: {stack_name}")
    template_body = load_template_body(template_path)
    parameters = load_parameters(parameters_path)

    try:
        cf.describe_stacks(StackName=stack_name)
        operation = "update_stack"
    except ClientError as e:
        if "does not exist" in str(e):
            operation = "create_stack"
        else:
            raise

    try:
        if operation == "create_stack":
            response = cf.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=['CAPABILITY_NAMED_IAM'],
                OnFailure='DO_NOTHING'
            )
        else:
            response = cf.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=['CAPABILITY_NAMED_IAM']
            )
        print(f"[{operation.upper()}] Stack operation started: {response['StackId']}")
        wait_for_stack(stack_name, operation)
    except ClientError as e:
        if "No updates are to be performed" in str(e):
            print(f"[SKIP] No updates needed for {stack_name}")
        else:
            print(f"[ERROR] Failed to {operation} {stack_name}: {e}")
            raise

def wait_for_stack(stack_name, operation):
    expected_status = "CREATE_COMPLETE" if operation == "create_stack" else "UPDATE_COMPLETE"
    timeout, interval, elapsed = 900, 10, 0

    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        try:
            response = cf.describe_stacks(StackName=stack_name)
            status = response['Stacks'][0]['StackStatus']
            print(f"  → {stack_name} Status: {status}")
            if status == expected_status:
                print(f"[COMPLETE] Stack {stack_name} => {status}")
                return
            elif "FAILED" in status or "ROLLBACK" in status:
                raise Exception(f"Stack {stack_name} failed with status: {status}")
        except ClientError as e:
            print(f"[ERROR] Checking stack status failed: {e}")
            raise
    raise TimeoutError(f"Timeout waiting for stack {stack_name} to reach {expected_status}")

# ---------------------------
# MAIN EXECUTION
# ---------------------------
if __name__ == '__main__':
    for stack in STACKS:
        try:
            deploy_stack(stack["name"], stack["template"], stack["parameters"])
        except Exception as e:
            print(f"[FAILED] Error deploying {stack['name']}: {e}")
            sys.exit(1)
