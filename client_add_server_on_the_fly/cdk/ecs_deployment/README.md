# MCP on Amazon Bedrock - ECS Deployment Guide

This directory contains AWS CDK code to deploy the MCP (Model Context Protocol) application on Amazon ECS with Fargate, with complete automation including Docker image building and deployment.

## Architecture Overview

The deployment creates a fully managed, scalable containerized MCP application:

- **VPC**: 2 AZs with public/private subnets and NAT Gateway
- **ECS Cluster**: Fargate-based container orchestration  
- **ECR Repository**: Automatic Docker image storage
- **Application Load Balancer**: Internet-facing for external access
- **EFS File System**: Persistent storage for logs and temporary files
- **IAM Roles**: Task execution and Bedrock API access permissions
- **Security Groups**: Network access control
- **Auto Docker Build**: CDK automatically builds and pushes your application

## Prerequisites

### 1. **System Requirements**

#### **Node.js Version (Critical)**
```bash
# Install Node.js v20+ or v22+ (NOT v18)
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo dnf install -y nodejs

# Verify version
node --version  # Should show v22.x.x or v20.x.x
```

#### **AWS CLI & CDK**
```bash
# Install/Update CDK CLI
npm install -g aws-cdk

# Verify AWS credentials
aws sts get-caller-identity
```

#### **Python Environment**
```bash
# Python 3.9+ required
python3 --version

# Docker (for local testing - optional)
docker --version
```

### 2. **AWS Account Setup**

#### **Required IAM Permissions**
Your AWS user/role needs permissions for:
- **ECS**: Create clusters, services, task definitions
- **ECR**: Create repositories, push images  
- **EC2**: VPC, subnets, security groups, load balancers
- **IAM**: Create roles and policies
- **EFS**: Create file systems
- **CloudFormation**: Create/update stacks
- **Bedrock**: API access for model invocation

#### **Bedrock Model Access**
```bash
# Request access to required models in AWS Console:
# 1. Go to Bedrock Console → Model access
# 2. Request access for: Amazon Nova Pro, Nova Lite, Claude models
# 3. Wait for approval (usually immediate)
```

### 3. **Cloud9 Environment Setup (Recommended)**

#### **Create Cloud9 Environment**
- **Instance Type**: t3.medium or larger
- **Platform**: Amazon Linux 2023
- **Storage**: Start with 20GB (not default 10GB)

#### **Storage Configuration**
```bash
# Check current disk space
df -h

# If less than 10GB available, resize EBS volume:
# 1. Go to EC2 Console → Volumes
# 2. Find your Cloud9 volume → Modify Volume → Increase size to 30GB  
# 3. Reboot Cloud9 instance (critical step!)
# 4. Verify after reboot: df -h should show full size
```

#### **Environment Cleanup**
```bash
# Before deployment, clean up space
docker system prune -a --volumes --force
sudo dnf clean all
rm -rf */cdk.out/ */.venv/ **/__pycache__/
```

## Deployment Steps

### **Step 1: Navigate to ECS CDK Directory**
```bash
cd ~/environment/saas-mcp-reference-architecture/client_add_server_on_the_fly/cdk/ecs_deployment
```

### **Step 2: Verify Required Files**
Ensure these files exist:
- `ecs_app.py` - CDK application entry point
- `ecs_mcp_stack.py` - ECS infrastructure definition  
- `requirements.txt` - Python CDK dependencies
- `cdk.json` - CDK configuration
- `../../.dockerignore` - Docker build exclusions
- `../../Dockerfile` - Application container definition

### **Step 3: Set Up Python Environment**
```bash
# Create fresh virtual environment
python3 -m venv .venv

# Activate virtual environment  
source .venv/bin/activate

# Install CDK dependencies
pip install -r requirements.txt

# Verify CDK installation
python -c "import aws_cdk; print('CDK ready')"
```

### **Step 4: CDK Bootstrap (First Time Only)**
```bash
# Bootstrap CDK with unique qualifier
QUALIFIER="mcp$(date +%H%M%S)"
echo "Using qualifier: $QUALIFIER"

cdk bootstrap --context qualifier=$QUALIFIER
```

### **Step 5: Deploy Complete Stack**
```bash
# Deploy everything (takes 15-20 minutes)
cdk deploy --context qualifier=$QUALIFIER

# When prompted "Do you wish to deploy these changes (y/n)?", type: y
```

### **What Happens During Deployment:**
1. **CDK builds Docker image** from your Dockerfile
2. **Creates ECR repository** and pushes image  
3. **Provisions AWS infrastructure** (VPC, ECS, ALB, etc.)
4. **Deploys containerized application** on ECS Fargate
5. **Configures load balancer** for public access
6. **Sets up health checks** and auto-scaling

## Post-Deployment

### **Get Application URL**
```bash
# Extract load balancer URL from outputs
ALB_URL=$(aws cloudformation describe-stacks --stack-name EcsMcpStack-$QUALIFIER --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerUrl`].OutputValue' --output text)
echo "Your MCP Application: $ALB_URL"
```

### **Verify Deployment**
```bash
# Check ECS service status
CLUSTER=$(aws cloudformation describe-stacks --stack-name EcsMcpStack-$QUALIFIER --query 'Stacks[0].Outputs[?OutputKey==`EcsClusterName`].OutputValue' --output text)
SERVICE=$(aws cloudformation describe-stacks --stack-name EcsMcpStack-$QUALIFIER --query 'Stacks[0].Outputs[?OutputKey==`EcsServiceName`].OutputValue' --output text)

aws ecs describe-services --cluster $CLUSTER --services $SERVICE --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}' --output table
```

### **Access Your Application**
1. **Open the LoadBalancerUrl** in your browser
2. **Wait 2-3 minutes** for container startup (if just deployed)
3. **Test MCP functionality**:
   - Select Amazon Nova Pro or Claude model
   - Enable "Local File System I/O" MCP server
   - Try: `"list files in current directory"`
   - Try: `"what models are available?"`

## Stack Outputs

After successful deployment:
- **LoadBalancerUrl**: Public URL to access Streamlit UI
- **EcrRepositoryUri**: ECR repository for your Docker images
- **EcsClusterName**: ECS cluster name for management
- **EcsServiceName**: ECS service name for monitoring

## Configuration

The deployment uses these default environment variables:
- `AWS_REGION`: Auto-configured from deployment region
- `MCP_BASE_URL`: http://127.0.0.1:7002 (internal container communication)
- `CHATBOT_SERVICE_PORT`: 8502 (Streamlit UI)
- `MCP_SERVICE_PORT`: 7002 (MCP API service) 
- `API_KEY`: mcp-demo-key
- `MAX_TURNS`: 200

## Troubleshooting

### **Common Issues & Solutions**

#### **1. Node.js Version Error**
```
Error: Node 18 has reached end-of-life
```
**Solution:**
```bash
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo dnf install -y nodejs
npm install -g aws-cdk
```

#### **2. Docker Build Out of Space**
```
No space left on device
```
**Solution:**
```bash
# Check space
df -h

# Clean up
docker system prune -a --force
rm -rf */cdk.out/

# Resize EBS volume if needed (via AWS Console)
# Then reboot Cloud9 instance
```

#### **3. Container Image Not Found**
```
CannotPullContainerError: image not found
```
**Solution:** This is automatically handled by CDK's `from_asset()` - it builds and pushes the image for you.

#### **4. ECS Service Not Starting**
**Check container logs:**
```bash
aws logs tail /ecs/mcp-bedrock-* --follow --since 10m
```

#### **5. Load Balancer Not Responding**
**Check target health:**
```bash
# Wait 5-10 minutes after deployment for health checks
curl -I $ALB_URL
```

### **Monitoring Commands**

#### **Service Status**
```bash
# Check ECS service health
aws ecs describe-services --cluster $CLUSTER --services $SERVICE

# Check target group health  
aws elbv2 describe-target-health --target-group-arn $(aws elbv2 describe-target-groups --names "*MCP*" --query 'TargetGroups[0].TargetGroupArn' --output text)
```

#### **Application Logs**
```bash
# Real-time container logs
aws logs tail /ecs/mcp-bedrock-* --follow

# Recent errors
aws logs filter-log-events --log-group-name /ecs/mcp-bedrock-* --filter-pattern ERROR
```

## Cost Optimization

**Monthly Cost Estimate (~$80-120):**
- **Fargate**: ~$35-50 (2048 CPU, 4096 MB memory)
- **ALB**: ~$16 + data processing charges
- **EFS**: ~$0.30/GB for stored data
- **NAT Gateway**: ~$32 + data processing
- **ECR**: ~$0.10/GB for image storage

**Cost Reduction Options:**
- Use scheduled scaling to shut down during off-hours
- Reduce container size (CPU/memory) if sufficient
- Consider EC2 launch type instead of Fargate
- Use ECS service auto-scaling based on demand

## Cleanup

### **Complete Cleanup**
```bash
# Destroy the entire stack
cdk destroy --context qualifier=$QUALIFIER

# Confirm when prompted
# This removes all AWS resources and associated costs
```

### **Manual Cleanup (if CDK destroy fails)**
```bash
# Delete ECR images first
aws ecr batch-delete-image --repository-name mcp-bedrock-* --image-ids imageTag=latest

# Then delete stack
aws cloudformation delete-stack --stack-name EcsMcpStack-$QUALIFIER
```

## Security Considerations

- **Network Isolation**: ECS tasks run in private subnets
- **Load Balancer**: Only ALB is internet-facing on port 80
- **Encryption**: EFS uses encryption in transit
- **IAM**: Least-privilege roles for task execution and Bedrock access
- **Security Groups**: Restrict network access appropriately

## Customization

### **Modify Container Resources**
Edit `ecs_mcp_stack.py`:
```python
task_definition = ecs.FargateTaskDefinition(
    # ...
    cpu=1024,        # Reduce CPU
    memory_limit_mib=2048,  # Reduce memory
)
```

### **Add Auto-Scaling**
```python
# Add to ECS service configuration
scaling = service.auto_scale_task_count(
    min_capacity=1,
    max_capacity=10
)
scaling.scale_on_cpu_utilization(
    "CpuScaling",
    target_utilization_percent=70
)
```

### **Add HTTPS/SSL**
```python
# Add certificate and HTTPS listener to ALB
certificate = acm.Certificate.from_certificate_arn(
    self, "Certificate", "arn:aws:acm:region:account:certificate/cert-id"
)
listener.add_certificates("Cert", [certificate])
```

## Lessons Learned

### **Key Success Factors:**
1. **Use Node.js v20+** - v18 is deprecated and causes issues
2. **Ensure adequate disk space** - 20GB minimum for Cloud9  
3. **Always reboot after EBS resize** - Required for filesystem expansion
4. **Use CDK's automatic Docker building** - Much simpler than manual ECR push
5. **Wait for health checks** - Allow 5-10 minutes after deployment

### **Best Practices:**
- Clean up Docker artifacts before deployment
- Use unique qualifiers to avoid naming conflicts  
- Monitor ECS service events during deployment
- Test locally with Docker before CDK deployment
- Keep CDK dependencies updated

## Support

### **For AWS Resource Issues:**
- Check CloudFormation events in AWS Console
- Monitor ECS service events and task definitions
- Review CloudWatch logs for application errors

### **For Application Issues:**
- Check container logs via CloudWatch
- Verify Bedrock model access permissions
- Test MCP server functionality locally first

### **For CDK Issues:**
- Ensure all dependencies are properly installed
- Verify AWS credentials and permissions
- Check CDK version compatibility

---

## Quick Start Summary

```bash
# Complete deployment in one go:
cd ~/environment/saas-mcp-reference-architecture/client_add_server_on_the_fly/cdk/ecs_deployment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
QUALIFIER="mcp$(date +%H%M%S)"
cdk bootstrap --context qualifier=$QUALIFIER
cdk deploy --context qualifier=$QUALIFIER
```

**Result**: Fully automated, production-ready MCP application accessible via public URL with complete AWS infrastructure managed by CDK.