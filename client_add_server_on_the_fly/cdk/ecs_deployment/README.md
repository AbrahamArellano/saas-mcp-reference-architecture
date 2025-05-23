# MCP on Amazon Bedrock - ECS Deployment

This directory contains AWS CDK code to deploy the MCP (Model Context Protocol) application on Amazon ECS with Fargate.

## Architecture Overview

The deployment creates:

- **VPC**: 2 AZs with public/private subnets and NAT Gateway
- **ECS Cluster**: Fargate-based container orchestration
- **ECR Repository**: Store Docker images
- **Application Load Balancer**: Internet-facing for external access
- **EFS File System**: Persistent storage for logs and temporary files
- **IAM Roles**: Task execution and Bedrock API access permissions
- **Security Groups**: Network access control

## Prerequisites

1. **AWS CLI** installed and configured
2. **Node.js** v20+ (for CDK CLI)
3. **Python** 3.9+ 
4. **Docker** (for building images)
5. **AWS CDK CLI**: `npm install -g aws-cdk`

## Required IAM Permissions

Your AWS user/role needs permissions for:
- ECS (create clusters, services, task definitions)
- ECR (create repositories, push images)
- EC2 (VPC, subnets, security groups, load balancers)
- IAM (create roles and policies)
- EFS (create file systems)
- CloudFormation (create/update stacks)
- Bedrock API access

## Deployment Steps

### 1. Navigate to ECS Deployment Directory

```bash
cd client_add_server_on_the_fly/cdk/ecs_deployment
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Bootstrap and Deploy CDK

```bash
# Bootstrap CDK (first time only)
cdk bootstrap --qualifier ecs123

# Deploy the stack
cdk deploy --qualifier ecs123
```

### 4. Build and Push Docker Image

After the first deployment, you'll get the ECR repository URI in the outputs:

```bash
# Get the ECR repository URI from the deployment outputs
ECR_URI=$(aws cloudformation describe-stacks --stack-name EcsMcpStack-ecs123 --query 'Stacks[0].Outputs[?OutputKey==`EcrRepositoryUri`].OutputValue' --output text)

# Go back to the main application directory
cd ../../

# Build Docker image
docker build -t mcp-bedrock .

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URI

# Tag and push image
docker tag mcp-bedrock:latest $ECR_URI:latest
docker push $ECR_URI:latest
```

### 5. Update ECS Service

```bash
# Get cluster and service names from outputs
CLUSTER_NAME=$(aws cloudformation describe-stacks --stack-name EcsMcpStack-ecs123 --query 'Stacks[0].Outputs[?OutputKey==`EcsClusterName`].OutputValue' --output text)
SERVICE_NAME=$(aws cloudformation describe-stacks --stack-name EcsMcpStack-ecs123 --query 'Stacks[0].Outputs[?OutputKey==`EcsServiceName`].OutputValue' --output text)

# Force ECS service to pull the new image
aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --force-new-deployment
```

## Stack Outputs

After successful deployment:

- **LoadBalancerUrl**: Public URL to access the Streamlit UI
- **EcrRepositoryUri**: ECR repository URI for Docker images  
- **EcsClusterName**: ECS cluster name
- **EcsServiceName**: ECS service name

## Accessing the Application

1. **Web UI**: Open the LoadBalancerUrl in your browser
2. **Wait**: Allow 2-3 minutes for the ECS service to become healthy
3. **Features**: Full MCP functionality with Bedrock integration

## Configuration

The deployment uses these environment variables:

- `AWS_REGION`: Auto-configured
- `MCP_BASE_URL`: http://127.0.0.1:7002
- `CHATBOT_SERVICE_PORT`: 8502
- `MCP_SERVICE_PORT`: 7002
- `API_KEY`: mcp-demo-key
- `MAX_TURNS`: 200

## Troubleshooting

### Service Not Starting
```bash
# Check ECS service events
aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME

# Check CloudWatch logs
aws logs tail /ecs/mcp-bedrock-* --follow
```

### Image Pull Errors
```bash
# Verify ECR repository exists and image is pushed
aws ecr list-images --repository-name mcp-bedrock-*
```

### Health Check Failures
```bash
# Check target group health
aws elbv2 describe-target-health --target-group-arn $(aws elbv2 describe-target-groups --names McpTargetGroup --query 'TargetGroups[0].TargetGroupArn' --output text)
```

## Cost Optimization

- **Fargate**: ~$30-50/month for single task running continuously
- **ALB**: ~$16/month + data processing charges
- **EFS**: ~$0.30/GB/month for stored data
- **NAT Gateway**: ~$32/month + data processing

To reduce costs:
- Use ECS service auto-scaling based on demand
- Consider using EC2 launch type instead of Fargate
- Use scheduled scaling to shut down during off-hours

## Cleanup

To delete all resources:

```bash
# Destroy the stack
cdk destroy --qualifier ecs123

# Manually delete ECR images if repository deletion fails
aws ecr batch-delete-image --repository-name mcp-bedrock-* --image-ids imageTag=latest
```

## Security Considerations

- ECS tasks run in private subnets with no direct internet access
- Only the ALB is internet-facing on port 80
- EFS uses encryption in transit
- IAM roles follow least-privilege principle
- Security groups restrict network access appropriately

## Customization

To modify the deployment:

1. **Change instance size**: Modify `cpu` and `memory_limit_mib` in task definition
2. **Add auto-scaling**: Add ECS service auto-scaling configuration
3. **Add HTTPS**: Configure ALB with SSL certificate
4. **Add monitoring**: Add CloudWatch alarms and dashboards
5. **Add domains**: Configure Route 53 and custom domain names

## Support

For issues with:
- **AWS Resources**: Check CloudFormation events and CloudWatch logs
- **Application**: Check ECS service logs and container health
- **Networking**: Verify security groups and target group health
- **CDK**: Ensure all dependencies are installed and AWS credentials are configured