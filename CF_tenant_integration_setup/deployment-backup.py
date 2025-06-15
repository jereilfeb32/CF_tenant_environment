def main():
    base_path = "./templates/"
    params_path = "./parameters.json"

    base_params = load_parameters(params_path)

    # Debugging output for parameters
    print("Loaded parameters:", base_params)

    # 1. Deploy VPC stack
    vpc_template = read_template_file(base_path + "vpc.yaml")
    vpc_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcCidr": base_params.get("VpcCidr")
    }
    deploy_stack("VpcStack", vpc_template, vpc_params)
    vpc_id = get_stack_output("VpcStack", "VpcId")
    print(f"VpcStack VpcId: {vpc_id}")

    # 2. Deploy IGW stack
    igw_template = read_template_file(base_path + "igw.yaml")
    igw_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcId": vpc_id
    }
    deploy_stack("IgwStack", igw_template, igw_params)
    igw_id = get_stack_output("IgwStack", "InternetGatewayId")
    print(f"IgwStack InternetGatewayId: {igw_id}")

    # 3. Deploy VGW stack
    vgw_template = read_template_file(base_path + "vgw.yaml")
    vgw_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcId": vpc_id
    }
    deploy_stack("VgwStack", vgw_template, vgw_params)
    vgw_id = get_stack_output("VgwStack", "VpnGatewayId")
    print(f"VgwStack VpnGatewayId: {vgw_id}")

    # 4. Deploy Subnets Stack
    subnets_template = read_template_file(base_path + "subnets.yaml")
    subnets_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcId": vpc_id,
        "AvailabilityZones": base_params.get("AvailabilityZones"),
        "PublicSubnetCidrs": base_params.get("PublicSubnetCidrs"),
        "PrivateSubnetCidrs": base_params.get("PrivateSubnetCidrs"),
        "ALBSubnetCidrs": base_params.get("ALBSubnetCidrs"),
        "GWLBSubnetCidrs": base_params.get("GWLBSubnetCidrs"),
        "SFTPSubnetCidrs": base_params.get("SFTPSubnetCidrs"),
        "VPCEndpointSubnetCidrs": base_params.get("VPCEndpointSubnetCidrs"),
        "ApiGatewaySubnetCidrs": base_params.get("ApiGatewaySubnetCidrs")
    }
    deploy_stack("SubnetStack", subnets_template, subnets_params)

    # Get subnet IDs
    public_subnet_ids = get_stack_output("SubnetStack", "PublicSubnetIds")
    private_subnet_ids = get_stack_output("SubnetStack", "PrivateSubnetIds")
    alb_subnet_ids = get_stack_output("SubnetStack", "ALBSubnetIds")
    gwlb_subnet_ids = get_stack_output("SubnetStack", "GWLBSubnetIds")
    sftp_subnet_ids = get_stack_output("SubnetStack", "SFTPSubnetIds")
    vpce_subnet_ids = get_stack_output("SubnetStack", "VPCEndpointSubnetIds")
    api_gateway_subnet_ids = get_stack_output("SubnetStack", "ApiGatewaySubnetIds")  # Added this line

    # 5. Deploy Security Groups stack
    secgroups_template = read_template_file(base_path + "security-groups.yaml")
    secgroups_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcId": vpc_id
    }
    deploy_stack("SecurityGroupsStack", secgroups_template, secgroups_params)

    # Get security group IDs
    alb_sg_id = get_stack_output("SecurityGroupsStack", "ALBSecurityGroupId")
    tgtgrp_sg_id = get_stack_output("SecurityGroupsStack", "TargetGroupSecurityGroupId")
    gwlb_sg_id = get_stack_output("SecurityGroupsStack", "GWLBSecurityGroupId")
    sftp_sg_id = get_stack_output("SecurityGroupsStack", "SFTPSecurityGroupId")
    apigwe_sg_id = get_stack_output("SecurityGroupsStack", "ApiGatewayEndpointSecurityGroupId")

    # 6. Deploy Route Tables Stack
    route_tables_template = read_template_file(base_path + "route-tables.yaml")
    route_tables_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcId": vpc_id,
        "InternetGatewayId": igw_id,
        "PublicSubnetIds": public_subnet_ids,
        "PrivateSubnetIds": private_subnet_ids,
        "ALBSubnetIds": alb_subnet_ids,
        "GWLBSubnetIds": gwlb_subnet_ids,
        "SFTPSubnetIds": sftp_subnet_ids,
        "VPCEndpointSubnetIds": vpce_subnet_ids,
        "ApiGatewayEndpointIds": api_gateway_subnet_ids  # Added this line
    }
    deploy_stack("RouteTablesStack", route_tables_template, route_tables_params)

    # 7. Deploy Route53 Private Hosted Zone
    route53_template = read_template_file(base_path + "route53-private-hosted-zone.yaml")
    route53_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcId": vpc_id,
        "DomainName": base_params.get("DomainName")
    }
    deploy_stack("Route53Stack", route53_template, route53_params)
    hosted_zone_id = get_stack_output("Route53Stack", "HostedZoneId")
    print(f"Route53Stack HostedZoneId: {hosted_zone_id}")

    # 8. Deploy WAF Stack
    waf_template = read_template_file(base_path + "waf.yaml")
    waf_params = {
        "ProjectName": base_params.get("ProjectName")  # Pass ProjectName parameter
    }
    deploy_stack("WAFStack", waf_template, waf_params)
    waf_arn = get_stack_output("WAFStack", "WebACLArn")
    print(f"WAFStack WebACLArn: {waf_arn}")

    # 9. Deploy ALB Stack
    alb_template = read_template_file(base_path + "alb.yaml")
    alb_params = {
        "ProjectName": base_params.get("ProjectName"),
        "ALBSubnetIds": alb_subnet_ids,
        "ALBSecurityGroupId": alb_sg_id,
        "TargetGroupSecurityGroupId": tgtgrp_sg_id,
        "ACMCertificateArn": base_params.get("ACMCertificateArn"),  # Use the ACM certificate ARN
        "WAFWebACLArn": waf_arn,
        "VpcId": vpc_id  # Pass the VPC ID to the ALB stack
    }
    deploy_stack("ALBStack", alb_template, alb_params)

    # 10. Deploy API Gateway VPC Endpoint Stack
    api_gateway_template = read_template_file(base_path + "api-gateway-endpoint.yaml")
    api_gateway_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcId": vpc_id,
        "PrivateSubnetIds": api_gateway_subnet_ids,  # Use ApiGatewaySubnetIds here
        "SecurityGroupIds": apigwe_sg_id  # Use the correct security group for API Gateway
    }
    deploy_stack("ApiGatewayVpcEndpointStack", api_gateway_template, api_gateway_params)

    # 11. Deploy SFTP Endpoint Stack
    sftp_template = read_template_file(base_path + "sftp-endpoint.yaml")
    sftp_params = {
        "ProjectName": base_params.get("ProjectName"),
        "VpcId": vpc_id,
        "SubnetIds": sftp_subnet_ids,  # Corrected to use SubnetIds
        "SecurityGroupIds": sftp_sg_id  # Corrected to use SecurityGroupIds
    }
    deploy_stack("SFTPStack", sftp_template, sftp_params)

    # 12. # Deploy GWLB VPC Endpoint Stack - pending, commented out for later
    # gwlb_vpce_template = read_template_file(base_path + "gwlb.yaml")
    # gwlb_vpce_params = {
    #     "ProjectName": base_params.get("ProjectName"),
    #     "VpcId": vpc_id,
    #     # Add other necessary parameters here
    # }
    # deploy_stack("GwlbVpcEndpointStack", gwlb_vpce_template, gwlb_vpce_params)

    print("All stacks deployed successfully.")

if __name__ == "__main__":
    main()
