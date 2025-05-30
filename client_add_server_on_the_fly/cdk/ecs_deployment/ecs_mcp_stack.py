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

        # 1. CREATE COGNITO USER POOL
        user_pool = cognito.UserPool(
            self, "McpUserPool",
            user_pool_name=f"mcp-users-{suffix}",
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False  # Optional for easier PoC testing
            ),
            # Standard attributes
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                given_name=cognito.StandardAttribute(required=False, mutable=True),
                family_name=cognito.StandardAttribute(required=False, mutable=True)
            ),
            # Account recovery
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=cdk.RemovalPolicy.DESTROY  # PoC only
        )

        # 2. CREATE COGNITO DOMAIN  
        cognito_domain = cognito.UserPoolDomain(
            self, "McpCognitoDomain",
            user_pool=user_pool,
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"mcp-auth-{suffix}"  # Globally unique
            )
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

        # 3. CREATE APPLICATION LOAD BALANCER
        alb = elbv2.ApplicationLoadBalancer(
            self, "McpLoadBalancer",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_security_group,
            load_balancer_name=f"mcp-alb-{suffix}"
        )

        # 4. CREATE SSL CERTIFICATE
        # Note: For PoC, we'll use a self-signed certificate approach
        # In production, you'd want to use a proper domain with Route53
        certificate = acm.Certificate(
            self, "McpCertificate",
            domain_name=alb.load_balancer_dns_name,
            validation=acm.CertificateValidation.from_dns(),
            # Note: This will create a certificate but DNS validation won't work 
            # without a proper domain. For PoC, you might want to use HTTP instead
        )

        # 5. CREATE COGNITO APP CLIENT (after ALB exists)
        app_client = cognito.UserPoolClient(
            self, "McpAppClient",
            user_pool=user_pool,
            user_pool_client_name=f"mcp-app-client-{suffix}",
            generate_secret=True,  # Required for ALB integration
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
                admin_user_password=True  # For admin operations
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=False  # More secure
                ),
                scopes=[
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE
                ],
                callback_urls=[
                    f"https://{alb.load_balancer_dns_name}/oauth2/idpresponse",
                    f"http://{alb.load_balancer_dns_name}/oauth2/idpresponse"  # For testing
                ],
                logout_urls=[
                    f"https://{alb.load_balancer_dns_name}/",
                    f"http://{alb.load_balancer_dns_name}/"
                ]
            ),
            # Session configuration
            access_token_validity=cdk.Duration.hours(1),
            id_token_validity=cdk.Duration.hours(1),
            refresh_token_validity=cdk.Duration.days(30)
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

        # Add container to task definition with Cognito environment variables
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
                "MAX_TURNS": "200",
                # Cognito Configuration
                "COGNITO_REGION": self.region,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_APP_CLIENT_ID": app_client.user_pool_client_id,
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

        # Allow ALB to reach ECS on port 8502
        ecs_security_group.add_ingress_rule(
            peer=alb_security_group,
            connection=ec2.Port.tcp(8502),
            description="Allow ALB to reach Streamlit UI"
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

        # Create Target Group
        target_group = elbv2.ApplicationTargetGroup(
            self, "McpTargetGroup",
            port=8502,
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=vpc,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                enabled=True,
                path="/_stcore/health",  # Streamlit health check endpoint
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

        # For PoC: Create HTTP listener with Cognito auth (since SSL cert might not validate immediately)
        http_listener = alb.add_listener(
            "HttpListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.authenticate_cognito(
                user_pool=user_pool,
                user_pool_client=app_client,
                user_pool_domain=cognito_domain,
                scope="openid email profile",
                next_action=elbv2.ListenerAction.forward([target_group])
            )
        )

        # 7. CREATE HTTPS LISTENER WITH COGNITO AUTH (if you have a valid domain)
        # Uncomment this section if you have a proper domain and valid SSL certificate
        """
        https_listener = alb.add_listener(
            "HttpsListener",
            port=443,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            certificates=[certificate],
            default_action=elbv2.ListenerAction.authenticate_cognito(
                user_pool=user_pool,
                user_pool_client=app_client,
                user_pool_domain=cognito_domain,
                scope="openid email profile",
                next_action=elbv2.ListenerAction.forward([target_group])
            )
        )

        # HTTP redirect to HTTPS
        alb.add_listener(
            "HttpRedirectListener", 
            port=80,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443",
                permanent=True
            )
        )
        """

        # Create a test user (Optional - for PoC testing)
        test_user = cognito.CfnUserPoolUser(
            self, "TestUser",
            user_pool_id=user_pool.user_pool_id,
            username="testuser",
            user_attributes=[
                cognito.CfnUserPoolUser.AttributeTypeProperty(
                    name="email",
                    value="test@example.com"
                ),
                cognito.CfnUserPoolUser.AttributeTypeProperty(
                    name="email_verified", 
                    value="true"
                )
            ],
            temporary_password="TempPass123!",
            message_action="SUPPRESS"  # Don't send welcome email for PoC
        )

        # Outputs
        cdk.CfnOutput(
            self, "LoadBalancerUrl",
            value=f"http://{alb.load_balancer_dns_name}",
            description="HTTP URL to access the MCP Application (with Cognito Auth)"
        )

        cdk.CfnOutput(
            self, "SecureApplicationUrl", 
            value=f"https://{alb.load_balancer_dns_name}",
            description="HTTPS URL (may require valid SSL cert setup)"
        )

        cdk.CfnOutput(
            self, "CognitoUserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID"
        )

        cdk.CfnOutput(
            self, "CognitoAppClientId",
            value=app_client.user_pool_client_id,
            description="Cognito App Client ID"
        )

        cdk.CfnOutput(
            self, "CognitoLoginUrl",
            value=f"https://{cognito_domain.domain_name}.auth.{self.region}.amazoncognito.com/login?client_id={app_client.user_pool_client_id}&response_type=code&scope=email+openid+profile&redirect_uri=http://{alb.load_balancer_dns_name}/oauth2/idpresponse",
            description="Direct Cognito Login URL"
        )

        cdk.CfnOutput(
            self, "TestUserCredentials",
            value="Username: testuser, Initial Password: TempPass123! (you'll be prompted to change)",
            description="Test user credentials for PoC"
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