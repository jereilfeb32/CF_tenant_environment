import boto3
import json
import os
import time
import sys
import logging
from botocore.exceptions import ClientError, BotoCoreError

# ---------------------------
# CONFIGURE LOGGING
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("deployment.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------
# AWS CLIENT SETUP
# ---------------------------
try:
    cf = boto3.client('cloudformation')
except (BotoCoreError, ClientError) as e:
    logger.exception("Failed to create CloudFormation client.")
    sys.exit(1)

# ---------------------------
# STACK DEFINITIONS
# ---------------------------
STACKS = [
    {
        "name": "perimeterVPCstack",
        "template": os.path.abspath(os.path.join("templates", "vpc.yaml")),
        "parameters": os.path.abspath(os.path.join("parameters", "parameters.json")),
    },
    {
        "name": "perimeterSGStack",
        "template": os.path.abspath(os.path.join("templates", "ngfw-security-group.yaml")),
        "parameters": os.path.abspath(os.path.join("parameters", "ngfw-sg-parameters.json")),
    },
    {
        "name": "perimeterGWLBStack",
        "template": os.path.abspath(os.path.join("templates", "gwlb.yaml")),
        "parameters": os.path.abspath(os.path.join("parameters", "gwlb-parameters.json")),
    },
    {
        "name": "perimeterec2Stack",
        "template": os.path.abspath(os.path.join("templates", "ec2-appliance.yaml")),
        "parameters": os.path.abspath(os.path.join("parameters", "ngfw-parameters.json")),
    },
    {
        "name": "perimetergwlbeStack",
        "template": os.path.abspath(os.path.join("templates", "gwlb-endpoints.yaml")),
        "parameters": os.path.abspath(os.path.join("parameters", "gwlbe-parameters.json")),
    },
    # Add more stacks here as needed
]

# ---------------------------
# HELPER FUNCTIONS
# ---------------------------

def load_parameters(file_path):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Parameter file not found: {file_path}")
    try:
        with open(file_path, 'r') as f:
            params = json.load(f)
            if not isinstance(params, list):
                raise ValueError("Parameters JSON must be a list of dicts")
            for p in params:
                if 'ParameterKey' not in p or 'ParameterValue' not in p:
                    raise ValueError(f"Malformed parameter: {p}")
            logger.info(f"Loaded parameters from {file_path}")
            return params
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        raise

def deploy_stack(stack_name, template_path, parameters_path=None, parameters=None):
    logger.info(f"[START] Deploying stack: {stack_name}")

    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")

    with open(template_path, 'r') as tf:
        template_body = tf.read()

    if parameters is None:
        parameters = load_parameters(parameters_path) if parameters_path else []

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
            cf.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=['CAPABILITY_NAMED_IAM'],
                OnFailure='DO_NOTHING',
                EnableTerminationProtection=False
            )
        else:
            cf.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=['CAPABILITY_NAMED_IAM']
            )
        logger.info(f"{operation.replace('_', ' ').title()} initiated for {stack_name}")
    except ClientError as e:
        if "No updates are to be performed" in str(e):
            logger.info(f"No updates needed for {stack_name}")
            return
        logger.error(f"Failed to {operation} stack {stack_name}: {e}")
        raise

    wait_for_stack_completion(stack_name, operation)

def wait_for_stack_completion(stack_name, operation):
    timeout = 900  # 15 minutes
    interval = 10
    elapsed = 0
    expected = "CREATE_COMPLETE" if operation == "create_stack" else "UPDATE_COMPLETE"

    logger.info(f"Waiting for stack '{stack_name}' to reach '{expected}'...")

    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        try:
            response = cf.describe_stacks(StackName=stack_name)
            stack = response['Stacks'][0]
            status = stack['StackStatus']
            logger.info(f"{stack_name} Status: {status}")
            if status == expected:
                logger.info(f"[COMPLETE] Stack {stack_name} => {status}")
                return
            elif "FAILED" in status or "ROLLBACK" in status:
                raise Exception(f"Stack {stack_name} failed with status: {status}")
        except ClientError as e:
            error_message = str(e)
            if "does not exist" in error_message:
                logger.error(f"Stack {stack_name} was deleted (likely due to OnFailure='DELETE').")
                raise Exception(f"Stack {stack_name} was deleted during creation. Check CloudFormation events for failure reason.")
            else:
                logger.error(f"Error fetching stack status: {e}")
                raise

    raise TimeoutError(f"Timeout waiting for stack {stack_name} to reach {expected}")

# ---------------------------
# MAIN EXECUTION
# ---------------------------
if __name__ == "__main__":
    try:
        for stack in STACKS:
            parameters = load_parameters(stack.get("parameters")) if stack.get("parameters") else []
            deploy_stack(
                stack_name=stack["name"],
                template_path=stack["template"],
                parameters=parameters
            )
    except Exception as e:
        logger.exception(f"[FAILED] Deployment pipeline stopped: {e}")
        sys.exit(1)
