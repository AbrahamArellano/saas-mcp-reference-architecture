# MCP on Amazon Bedrock - ECS Deployment

This project deploys a Model Context Protocol (MCP) server on Amazon ECS with Fargate, integrated with Amazon Bedrock.

## Domain Configuration

This deployment supports two options for domain configuration:

### Option 1: Route53 and CloudFront (Default)

1. Ensure you have a Route53 hosted zone set up for your domain
2. Create or import an SSL/TLS certificate in AWS Certificate Manager
3. Set the required environment variables in `set_variables.sh`:
   - `CDK_QUALIFIER`: Qualifier for the stack (required)
   - `CERTIFICATE_ARN`: ARN of your SSL/TLS certificate
   - `HOSTED_ZONE_ID`: ID of your Route53 hosted zone
   - `ZONE_NAME`: Your domain name (e.g., example.com)
   - `RECORD_NAME_MCP`: Subdomain for the MCP application (e.g., mcp.example.com)
   - `CLOUDFRONT_PREFIX_LIST_ID`: (Optional) CloudFront prefix list ID for enhanced security

### Option 2: Custom Domain Name (Alternative)

If you prefer not to use Route53, you can use a custom domain name:

1. Set the required environment variables in `set_variables.sh`:
   - `CDK_QUALIFIER`: Qualifier for the stack (required)
   - `DOMAIN_NAME`: Your custom domain name

   Note: With this option, the CDK will automatically create an ACM certificate for your domain with DNS validation. You'll need to create the necessary DNS records to validate the certificate.

2. Deploy with the domain_name deployment type (see Deployment Steps)

4. Source the variables:
   ```bash
   source set_variables.sh
   ```

5. Deploy the stack with the qualifier:
   ```bash
   cdk deploy --qualifier $CDK_QUALIFIER
   ```
   or
   ```bash
   cdk deploy --context qualifier=<your-qualifier>
   ```

## Prerequisites

- AWS CDK installed
- Docker installed
- AWS CLI configured
- A domain name with a Route53 hosted zone
- An SSL/TLS certificate in AWS Certificate Manager

## Deployment Steps

1. **Set up Python environment** (if not already done):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Bootstrap CDK** (first time only):
   ```bash
   QUALIFIER="mcp$(date +%H%M%S)"
   cdk bootstrap --context qualifier=$QUALIFIER
   ```

3. **Configure environment variables**:
   ```bash
   source set_variables.sh
   ```

4. **Deploy the stack with qualifier**:
   
   For Route53-based deployment (default):
   ```bash
   cdk deploy --context qualifier=$QUALIFIER
   ```
   
   For domain name-based deployment:
   ```bash
   cdk deploy --context qualifier=$QUALIFIER --context deployment_type=domain_name
   ```
   
   Or using environment variable:
   ```bash
   export DEPLOYMENT_TYPE=domain_name
   cdk deploy --context qualifier=$QUALIFIER
   ```

5. **Access the application** at the URL provided in the output.

## Security

This deployment includes several security features:
- CloudFront distribution with HTTPS
- Cognito authentication
- Security groups with least privilege
- Optional CloudFront prefix list for enhanced security

## Architecture

The deployment includes:
- Amazon ECS with Fargate
- Application Load Balancer
- Amazon CloudFront
- Amazon Cognito
- Amazon EFS
- Route53 DNS records

## Troubleshooting

### Common Issues

#### Docker Build Failures
```bash
# Clean up space and rebuild
docker system prune -a --volumes --force
rm -rf */cdk.out/
cdk deploy --context qualifier=$QUALIFIER
```

#### Application Not Responding
```bash
# Check container logs
aws logs tail /ecs/mcp-bedrock-* --follow --since 10m

# Verify health checks
curl -I <alb-url>/_stcore/health
```

## Cleanup

To remove all resources, use the same qualifier that was used during deployment:

```bash
# Replace QUALIFIER with the qualifier used during deployment
cdk destroy --context qualifier=$QUALIFIER
```

Or if you used a custom qualifier:
```bash
cdk destroy --qualifier $CDK_QUALIFIER
```

Note: This will delete all resources including the ECS tasks, ALB, and IAM roles. Make sure to backup any data before destroying the stack.
