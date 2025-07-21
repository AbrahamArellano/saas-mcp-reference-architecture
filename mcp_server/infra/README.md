# MCP Server Infrastructure

This directory contains the CDK project for deploying the MCP server infrastructure to AWS. For general information about the MCP server, deployment instructions, and architecture overview, please refer to the [top-level README](../README.md).

## Stack Architecture

The infrastructure is split into two separate stacks:

1. **MCPServerServicesStack** (`lib/services-stack.ts`):
   - **DynamoDB Table**: `MCPServerTravelBookings` for travel booking data
   - **S3 Bucket**: `MCPServerTravelPolicyBucket` for policy documents
   - **IAM Roles**: `MCPServerTaskRole` and `MCPServerDynamoDbAccessRole`
   - **Cognito User Pool**: For authentication and user management

2. **MCPServerApplicationStack** (`lib/application-stack.ts`):
   - **ECS Fargate Service**: Running the MCP server container
   - **Application Load Balancer**: Providing HTTP/HTTPS access
   - **VPC and Networking**: Subnets, security groups, etc.

## Deployment Options

### Using the Deployment Script

```bash
# Deploy both stacks
./deploy.sh

# Deploy only the services stack
./deploy.sh --services-only

# Deploy only the application stack
./deploy.sh --application-only

# Deploy with a specific certificate ARN for HTTPS
./deploy.sh --certificate arn:aws:acm:us-east-1:123456789012:certificate/abcd1234-...

# Show all available options
./deploy.sh --help
```

### Script Options

```
Usage: ./deploy.sh [options]

Options:
  -h, --help                 Show this help message
  --services-stack NAME      Set the services stack name (default: MCPServerServicesStack)
  --app-stack NAME           Set the application stack name (default: MCPServerApplicationStack)
  -c, --certificate ARN      Set the ACM certificate ARN
  -r, --repository NAME      Set the ECR repository name (default: mcp-server-on-ecs)
  -t, --image-tag TAG        Set the container image tag (default: latest)
  -a, --admin-role NAME      Set the admin role name (optional)
  -g, --region REGION        Set the AWS region (default: from AWS_REGION env var or us-east-1)
  -n, --no-rollback          Disable rollback on failure (default: true)
  --rollback                 Enable rollback on failure
  --services-only            Deploy only the services stack
  --application-only         Deploy only the application stack
```

### Manual Deployment

```bash
# Install dependencies
npm install

# Build the TypeScript code
npm run build

# Deploy the services stack
npx cdk deploy MCPServerServicesStack --exclusively

# Deploy the application stack
CERTIFICATE_ARN="your-certificate-arn" npx cdk deploy MCPServerApplicationStack --exclusively
```

## Infrastructure Details

### DynamoDB Table Design

The `MCPServerTravelBookings` table uses:
- Partition key: `PK` (prefixed with tenant ID for isolation)
- Sort key: `SK` (for organizing different booking types)
- On-demand capacity mode for cost optimization
- Point-in-time recovery enabled

### IAM Role Configuration

The `MCPServerDynamoDbAccessRole` includes:
- Condition keys for tenant isolation: `dynamodb:LeadingKeys`
- Session tagging for tenant context
- Least privilege permissions

### Cognito User Pool Configuration

- Email verification required
- Custom attributes for tenant information
- Password policies for security
- OAuth 2.0 configuration for hosted UI

### ECS Service Configuration

- Fargate launch type for serverless operation
- Auto-scaling based on CPU utilization
- Health checks on the `/health` endpoint
- Environment variables for configuration

## Setting up DNS (Optional)

To configure a custom domain name using Route 53:

1. **Get the ALB DNS name**:
   ```bash
   aws cloudformation describe-stacks --stack-name MCPServerApplicationStack \
     --query "Stacks[0].Outputs[?OutputKey=='MCPServerLoadBalancerDns'].OutputValue" \
     --output text
   ```

2. **Create an A record alias in Route 53**:
   ```bash
   aws route53 change-resource-record-sets \
     --hosted-zone-id YOUR_HOSTED_ZONE_ID \
     --change-batch '{
       "Changes": [
         {
           "Action": "CREATE",
           "ResourceRecordSet": {
             "Name": "mcp.yourdomain.com",
             "Type": "A",
             "AliasTarget": {
               "HostedZoneId": "YOUR_ALB_HOSTED_ZONE_ID",
               "DNSName": "your-alb-dns-name",
               "EvaluateTargetHealth": true
             }
           }
         }
       ]
     }'
   ```

## Cleanup

To remove all resources:

```bash
# Remove the application stack first
npx cdk destroy MCPServerApplicationStack

# Then remove the services stack
npx cdk destroy MCPServerServicesStack
```

## CDK Commands

* `npm run build` - Compile TypeScript to JS
* `npm run watch` - Watch for changes and compile
* `npm run test` - Perform the jest unit tests
* `npx cdk diff` - Compare deployed stack with current state
* `npx cdk synth` - Emit the synthesized CloudFormation template
