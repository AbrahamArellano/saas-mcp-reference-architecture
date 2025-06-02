import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecr as ecr,
    aws_logs as logs,
    aws_efs as efs,
    aws_cognito as cognito,
    aws_certificatemanager as acm,
    Stack
)
from constructs import Construct
import hashlib


class EcsMcpStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Generate unique suffix for naming
        unique_input = f"{self.account}-{self.region}"
        unique_hash = hashlib.sha256(unique_input.encode('utf-8')).hexdigest()[:8]
        suffix = unique_hash.lower()

        # Custom domain configuration
        domain_name = "mcp.myitbasics.com"

        # Create VPC
        vpc = ec2.Vpc(
            self, "McpVPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ]
        )

        # Create ECR Repository
        ecr_repository = ecr.Repository(
            self, "McpRepository",
            repository_name=f"mcp-bedrock-{suffix}",
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        # Create EFS File System for persistent storage
        efs_security_group = ec2.SecurityGroup(
            self, "EfsSecurityGroup",
            vpc=vpc,
            description="Security Group for EFS",
            allow_all_outbound=False
        )

        efs_file_system = efs.FileSystem(
            self, "McpEfs",
            vpc=vpc,
            security_group=efs_security_group,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
            throughput_mode=efs.ThroughputMode.ELASTIC
        )

        # Create ECS Cluster
        cluster = ecs.Cluster(
            self, "McpCluster",
            vpc=vpc,
            cluster_name=f"mcp-cluster-{suffix}",
            container_insights=True
        )

        # Create CloudWatch Log Group
        log_group = logs.LogGroup(
            self, "McpLogGroup",
            log_group_name=f"/ecs/mcp-bedrock-{suffix}",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK
        )

        # Create ACM Certificate for custom domain
        certificate = acm.Certificate(
            self, "McpCertificate",
            domain_name=domain_name,
            validation=acm.CertificateValidation.from_dns(),
            subject_alternative_names=[domain_name]  # Explicit SAN
        )

        # Create IAM Task Execution Role
        task_execution_role = iam.Role(
            self, "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ]
        )

        # Create IAM Task Role with Bedrock permissions
        task_role = iam.Role(
            self, "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "BedrockAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeModel*",
                                "bedrock:ListFoundationModels"
                            ],
                            resources=["*"]
                        )
                    ]
                ),
                "EfsAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "elasticfilesystem:ClientMount",
                                "elasticfilesystem:ClientRootAccess",
                                "elasticfilesystem:ClientWrite"
                            ],
                            resources=[efs_file_system.file_system_arn]
                        )
                    ]
                )
            }
        )

        # Create EFS Volume Configuration
        efs_volume_config = ecs.EfsVolumeConfiguration(
            file_system_id=efs_file_system.file_system_id,
            transit_encryption="ENABLED",
            authorization_config=ecs.AuthorizationConfig(
                iam="ENABLED"
            )
        )

        # Create Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self, "McpTaskDefinition",
            family=f"mcp-bedrock-{suffix}",
            cpu=2048,
            memory_limit_mib=4096,
            task_role=task_role,
            execution_role=task_execution_role,
            volumes=[
                ecs.Volume(
                    name="efs-storage",
                    efs_volume_configuration=efs_volume_config
                )
            ]
        )

        # Add container to task definition with automatic Docker build
        container = task_definition.add_container(
            "McpContainer",
            container_name="mcp-app",
            # CDK will automatically build and push Docker image
            image=ecs.ContainerImage.from_asset("../../"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="mcp-app",
                log_group=log_group
            ),
            environment={
                "AWS_REGION": self.region,
                "LOG_DIR": "/app/logs",
                "CHATBOT_SERVICE_PORT": "8502",
                "MCP_SERVICE_HOST": "127.0.0.1",
                "MCP_SERVICE_PORT": "7002",
                "MCP_BASE_URL": "http://127.0.0.1:7002",
                "API_KEY": "mcp-demo-key",
                "MAX_TURNS": "200"
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8502/_stcore/health || exit 1"],
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                retries=3,
                start_period=cdk.Duration.seconds(60)
            )
        )

        # Add port mappings
        container.add_port_mappings(
            ecs.PortMapping(
                container_port=8502,
                protocol=ecs.Protocol.TCP,
                name="streamlit-ui"
            ),
            ecs.PortMapping(
                container_port=7002,
                protocol=ecs.Protocol.TCP,
                name="mcp-api"
            )
        )

        # Add mount points for EFS
        container.add_mount_points(
            ecs.MountPoint(
                source_volume="efs-storage",
                container_path="/app/logs",
                read_only=False
            ),
            ecs.MountPoint(
                source_volume="efs-storage",
                container_path="/app/tmp",
                read_only=False
            )
        )

        # Create Security Group for ECS Service
        ecs_security_group = ec2.SecurityGroup(
            self, "EcsSecurityGroup",
            vpc=vpc,
            description="Security Group for ECS Service",
            allow_all_outbound=True
        )

        # Allow EFS access from ECS
        efs_security_group.add_ingress_rule(
            peer=ecs_security_group,
            connection=ec2.Port.tcp(2049),
            description="Allow NFS from ECS"
        )

        # Create ECS Service
        service = ecs.FargateService(
            self, "McpService",
            cluster=cluster,
            task_definition=task_definition,
            service_name=f"mcp-service-{suffix}",
            desired_count=1,
            assign_public_ip=False,
            security_groups=[ecs_security_group],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            health_check_grace_period=cdk.Duration.seconds(180)
        )

        # Create ALB Security Group
        alb_security_group = ec2.SecurityGroup(
            self, "AlbSecurityGroup",
            vpc=vpc,
            description="Security Group for Application Load Balancer",
            allow_all_outbound=True
        )

        # Allow HTTP and HTTPS access from anywhere
        alb_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP from anywhere"
        )
        alb_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS from anywhere"
        )

        # Allow ALB to reach ECS on port 8502
        ecs_security_group.add_ingress_rule(
            peer=alb_security_group,
            connection=ec2.Port.tcp(8502),
            description="Allow ALB to reach Streamlit UI"
        )

        # Create Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(
            self, "McpLoadBalancer",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_security_group,
            load_balancer_name=f"mcp-alb-{suffix}"
        )

        # Create Target Group
        target_group = elbv2.ApplicationTargetGroup(
            self, "McpTargetGroup",
            port=8502,
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=vpc,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                enabled=True,
                path="/_stcore/health",
                protocol=elbv2.Protocol.HTTP,
                port="8502",
                healthy_http_codes="200",
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3
            )
        )

        # Add ECS service to target group
        target_group.add_target(service)

        # Create HTTP listener (redirects to HTTPS)
        http_listener = alb.add_listener(
            "HttpListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443"
            )
        )

        # Create HTTPS listener
        https_listener = alb.add_listener(
            "HttpsListener",
            port=443,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            certificates=[certificate],
            default_action=elbv2.ListenerAction.forward([target_group])
        )

        # CREATE COGNITO USER POOL (ready for Phase 2)
        user_pool = cognito.UserPool(
            self, "McpUserPool",
            user_pool_name=f"mcp-users-{suffix}",
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            self_sign_up_enabled=True,
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False
            ),
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        # CREATE COGNITO DOMAIN  
        cognito_domain = cognito.UserPoolDomain(
            self, "McpCognitoDomain",
            user_pool=user_pool,
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"mcp-auth-{suffix}"
            )
        )

        # CREATE COGNITO APP CLIENT
        app_client = cognito.UserPoolClient(
            self, "McpAppClient",
            user_pool=user_pool,
            user_pool_client_name=f"mcp-app-client-{suffix}",
            generate_secret=True,
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
                admin_user_password=True
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=False
                ),
                scopes=[
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE
                ],
                callback_urls=[f"https://{domain_name}/"],
                logout_urls=[f"https://{domain_name}/"]
            ),
            access_token_validity=cdk.Duration.hours(1),
            id_token_validity=cdk.Duration.hours(1),
            refresh_token_validity=cdk.Duration.days(30)
        )

        # Outputs
        cdk.CfnOutput(
            self, "LoadBalancerUrl",
            value=f"https://{domain_name}",
            description="HTTPS URL to access the MCP Application"
        )

        cdk.CfnOutput(
            self, "LoadBalancerDnsName",
            value=alb.load_balancer_dns_name,
            description="ALB DNS name for CNAME record"
        )

        cdk.CfnOutput(
            self, "CertificateArn",
            value=certificate.certificate_arn,
            description="ACM Certificate ARN"
        )

        cdk.CfnOutput(
            self, "DNSValidationInstructions",
            value=f"Add CNAME record in Bluehost: mcp -> {alb.load_balancer_dns_name}",
            description="DNS setup instructions"
        )

        cdk.CfnOutput(
            self, "CognitoUserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID (for Phase 2)"
        )

        cdk.CfnOutput(
            self, "EcrRepositoryUri",
            value=ecr_repository.repository_uri,
            description="ECR Repository URI"
        )

        cdk.CfnOutput(
            self, "EcsClusterName",
            value=cluster.cluster_name,
            description="ECS Cluster Name"
        )

        cdk.CfnOutput(
            self, "EcsServiceName",
            value=service.service_name,
            description="ECS Service Name"
        )