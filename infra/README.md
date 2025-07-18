# MCP Server Infrastructure

This CDK project deploys the MCP (Model Context Protocol) server infrastructure to AWS. The deployment creates a containerized application running on ECS Fargate with multi-tenant data isolation.

## Architecture Overview

The infrastructure consists of two separate stacks:

1. **MCPServerServicesStack**: Contains the foundational resources
   - **MCPServerTravelBookings**: DynamoDB table for travel booking data with tenant isolation
   - **MCPServerTravelPolicyBucket**: S3 bucket for policy documents
   - **MCPServerTaskRole** and **MCPServerDynamoDbAccessRole**: IAM roles for secure access

2. **MCPServerApplicationStack**: Contains the application resources
   - **MCPServerFargateService**: ECS Fargate service running the MCP server container
   - **Application Load Balancer**: Provides HTTP/HTTPS access to the MCP Server
   - **VPC and Networking**: Includes VPC, subnets, security groups, etc.

## Deployment Workflow

The split architecture enables a streamlined development workflow:

1. **Local Development Phase**:
   ```bash
   # Deploy only the MCP Server services stack
   ./deploy.sh --services-only
   
   # Use the output values in your local .env file
   # TABLE_NAME=MCPServerTravelBookings
   # BUCKET_NAME=<bucket-name-from-stack-output>
   # ROLE_ARN=<dynamodb-access-role-arn-from-stack-output>
   
   # Develop and test locally against real AWS resources
   ```

2. **Container Build Phase**:
   ```bash
   # Build and push your MCP Server container to ECR
   cd ../server
   ./scripts/pushDockerImage.sh
   ```

3. **Application Deployment Phase**:
   ```bash
   # Deploy the MCP Server application stack
   cd ../infra
   ./deploy.sh --application-only --certificate <your-certificate-arn>
   ```

This workflow provides several advantages:
- **Consistency**: Your local development environment uses the same AWS resources as your deployed MCP Server
- **Efficiency**: You can iterate quickly locally before deploying the full infrastructure
- **Cost Optimization**: You can tear down the application stack when not in use while keeping your data resources
- **Separation of Concerns**: Clear distinction between data/permissions and application infrastructure

## Prerequisites

Before deploying this stack, ensure you have:

1. Built and pushed a container image to an ECR repository named `stateless-mcp-on-ecs` (or your custom name)
   - Use the `pushDockerImage.sh` script in the `server/scripts` directory to build and push the image
2. (Optional) A TLS certificate in ACM for HTTPS support
3. AWS CLI configured with appropriate permissions
4. Node.js and npm installed
5. Bootstrapped your AWS environment for CDK deployments

### Bootstrapping the CDK Environment

CDK requires a bootstrapping process to create the necessary resources for deployment. This only needs to be done once per AWS account and region:

```bash
# Bootstrap the CDK environment
npx cdk bootstrap
```

This creates resources like:
- An S3 bucket for storing assets
- IAM roles for deployment
- Other resources needed by CDK

## Environment Variables

The deployment can be customized with the following environment variables:

- `CERTIFICATE_ARN`: ARN of an ACM certificate for HTTPS (optional)
- `ADMIN_ROLE_NAME`: Name of an admin role that should have access (optional)
- `ECR_REPOSITORY_NAME`: Name of the ECR repository (default: "stateless-mcp-on-ecs")
- `IMAGE_TAG`: Tag of the container image to use (default: "latest")

## Deployment

### Using the Deployment Script

A deployment script is provided to simplify the deployment process. The script checks if the required ECR repository exists and sets up all required environment variables.

```bash
# Make the script executable if needed
chmod +x deploy.sh

# Run the deployment script with default options (deploys both stacks)
./deploy.sh

# Deploy only the MCP Server services stack
./deploy.sh --services-only

# Deploy only the MCP Server application stack (requires services stack to be deployed first)
./deploy.sh --application-only

# Show all available options
./deploy.sh --help
```

Available options:

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

Example usage:

```bash
# Deploy with a specific certificate ARN
./deploy.sh --certificate arn:aws:acm:us-east-1:123456789012:certificate/abcd1234-...

# Deploy with custom stack names
./deploy.sh --services-stack MyMCPServerServicesStack --app-stack MyMCPServerAppStack

# Deploy services stack with admin role
./deploy.sh --services-only --admin-role MyMCPServerAdminRole

# Deploy application stack with specific image tag
./deploy.sh --application-only --image-tag v1.0.0 --certificate arn:aws:acm:...

# Deploy with no rollback on failure (useful for debugging)
./deploy.sh --no-rollback
```

**Note**: The deployment script will check if the ECR repository exists and will fail if it doesn't. Make sure to run the `pushDockerImage.sh` script in the server directory first.

### Manual Deployment

To deploy the stack manually:

```bash
# Install dependencies
npm install

# Build the TypeScript code
npm run build

# Deploy the stack with environment variables
CERTIFICATE_ARN="your-certificate-arn" npx cdk deploy
```

## Security Features

### Multi-tenant Data Isolation

The stack implements tenant isolation using:

- STS session tagging for tenant context
- DynamoDB access control using the `dynamodb:LeadingKeys` condition
- Role-based access control for administrative functions

### Network Security

- Application Load Balancer with optional HTTPS support
- Health checks configured on the `/health` endpoint

## Post-Deployment Steps

After deployment:

1. Add DNS records pointing to the ALB (not handled by this CDK stack)
2. Configure your client applications with the appropriate endpoint URLs

### Setting up Route 53 DNS (Manual Process)

To configure a custom domain name for your MCP server using Route 53:

1. **Create or use an existing hosted zone in Route 53**:
   ```bash
   # Create a new hosted zone if needed
   aws route53 create-hosted-zone --name yourdomain.com --caller-reference $(date +%s)
   ```

2. **Get the ALB DNS name**:
   ```bash
   # Replace InfraStack with your stack name if different
   export ALB_DNS=$(aws cloudformation describe-stacks --stack-name InfraStack --query "Stacks[0].Outputs[?OutputKey=='McpServerServiceLoadBalancerDNS'].OutputValue" --output text)
   echo $ALB_DNS
   ```

3. **Create an A record alias pointing to the ALB**:
   ```bash
   # Replace with your hosted zone ID and domain name
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
               "DNSName": "'$ALB_DNS'",
               "EvaluateTargetHealth": true
             }
           }
         }
       ]
     }'
   ```
   
   Note: You'll need to get the ALB's hosted zone ID, which depends on the AWS region. You can find this in the AWS documentation or by checking the ALB details in the console.

4. **Update your ACM certificate**:
   Ensure your ACM certificate includes the domain name you're using (e.g., mcp.yourdomain.com). If not, you'll need to request a new certificate and update the CERTIFICATE_ARN environment variable before redeploying.

## Cleanup

The DynamoDB table and S3 bucket are configured with `DESTROY` removal policy, meaning they will be deleted when the stack is destroyed.

To remove all resources:

```bash
npx cdk destroy
```

## Useful Commands

* `npm run build`   compile TypeScript to JS
* `npm run watch`   watch for changes and compile
* `npm run test`    perform the jest unit tests
* `npx cdk deploy`  deploy this stack to your default AWS account/region
* `npx cdk diff`    compare deployed stack with current state
* `npx cdk synth`   emits the synthesized CloudFormation template
