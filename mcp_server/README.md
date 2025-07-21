# MCP Server

This directory contains a Model Context Protocol (MCP) server implementation that can be deployed to Amazon ECS. The server provides a set of tools and resources for a B2B Travel booking agent with enterprise-grade authentication via Amazon Cognito User Pool.

## Overview

The MCP server is built using:
- Node.js with Express
- AWS SDK for DynamoDB, S3, and STS
- MCP SDK for implementing the Model Context Protocol
- JWT with cryptographic verification for authentication
- Amazon Cognito User Pool for user management and token issuance

## Architecture

![Architecture Overview](../resources/mcp_server_architecture.png)

The infrastructure consists of two separate stacks:

1. **MCPServerServicesStack**: Contains the foundational resources
   - DynamoDB table for travel booking data with tenant isolation
   - S3 bucket for policy documents
   - IAM roles for secure access
   - Cognito User Pool for authentication

2. **MCPServerApplicationStack**: Contains the application resources
   - ECS Fargate service running the MCP server container
   - Application Load Balancer for HTTP/HTTPS access
   - VPC and networking components

## Quick Start

### Prerequisites

- Node.js 18+ (server uses Node.js 22 in production)
- AWS CLI configured with appropriate permissions
- Docker or Finch for container operations
- An AWS account with access to ECR, Cognito, DynamoDB, and S3

### Deployment Steps

1. **Deploy the Services Stack**:
   ```bash
   cd infra
   ./deploy.sh --services-only
   ```

2. **Build and Push the Docker Image**:
   ```bash
   cd ../src
   npm install
   
   # Build the Docker image locally
   ./scripts/buildDockerImage.sh
   
   # Or build and push to ECR in one step
   ./scripts/pushDockerImage.sh
   ```

3. **Deploy the Application Stack**:
   ```bash
   cd ../infra
   ./deploy.sh --application-only
   ```

4. **Access the MCP Server**:
   ```bash
   # Get the ALB DNS name
   aws cloudformation describe-stacks --stack-name MCPServerApplicationStack \
     --query "Stacks[0].Outputs[?OutputKey=='MCPServerLoadBalancerDns'].OutputValue" \
     --output text
   ```

## Authentication

The server implements secure JWT authentication using Amazon Cognito User Pool:

### Getting Authentication Tokens

```bash
# Get User Pool ID and Client ID
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name MCPServerServicesStack \
  --query "Stacks[0].Outputs[?OutputKey=='MCPServerUserPoolId'].OutputValue" --output text)
CLIENT_ID=$(aws cloudformation describe-stacks --stack-name MCPServerServicesStack \
  --query "Stacks[0].Outputs[?OutputKey=='MCPServerUserPoolClientId'].OutputValue" --output text)

# Get authentication tokens
aws cognito-idp admin-initiate-auth \
  --user-pool-id $USER_POOL_ID \
  --client-id $CLIENT_ID \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=your-username,PASSWORD=your-password
```

### Using Tokens with the MCP Server

```bash
# Extract the ID Token
ID_TOKEN=$(aws cognito-idp admin-initiate-auth \
  --user-pool-id $USER_POOL_ID \
  --client-id $CLIENT_ID \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=your-username,PASSWORD=your-password \
  --query "AuthenticationResult.IdToken" --output text)

# Call the MCP Server
curl -X POST https://your-mcp-server-url/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

## Development Workflow

### Local Development

1. **Deploy the Services Stack**:
   ```bash
   cd infra
   ./deploy.sh --services-only
   ```

2. **Configure Local Environment**:
   ```bash
   cd ../src
   
   # Create .env file with outputs from the services stack
   echo "TABLE_NAME=MCPServerTravelBookings" > .env
   echo "BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name MCPServerServicesStack --query "Stacks[0].Outputs[?OutputKey=='MCPServerPolicyBucketName'].OutputValue" --output text)" >> .env
   echo "ROLE_ARN=$(aws cloudformation describe-stacks --stack-name MCPServerServicesStack --query "Stacks[0].Outputs[?OutputKey=='MCPServerDynamoDbAccessRoleArn'].OutputValue" --output text)" >> .env
   echo "COGNITO_USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name MCPServerServicesStack --query "Stacks[0].Outputs[?OutputKey=='MCPServerUserPoolId'].OutputValue" --output text)" >> .env
   echo "COGNITO_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name MCPServerServicesStack --query "Stacks[0].Outputs[?OutputKey=='MCPServerUserPoolClientId'].OutputValue" --output text)" >> .env
   echo "AWS_REGION=us-east-1" >> .env
   ```

3. **Run Locally**:
   ```bash
   npm install
   npm start
   ```

### Testing

1. **Health Check**:
   ```bash
   curl -X GET http://localhost:3000/health
   ```

2. **MCP API with Authentication**:
   ```bash
   curl -X POST http://localhost:3000/mcp \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -H "Authorization: Bearer <your-token>" \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
   ```

3. **Whoami Tool (works without authentication)**:
   ```bash
   curl -X POST http://localhost:3000/mcp \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "whoami"}'
   ```

## Security Features

- **Multi-tenant Data Isolation**: Complete data isolation using DynamoDB partition keys
- **JWT Authentication**: Cryptographic verification of tokens using Cognito's public keys
- **STS Session Tagging**: AWS credentials tagged with tenant context
- **HTTPS Support**: Optional TLS certificates for encrypted communication

## Directory Structure

- **src/**: MCP server implementation
  - Core server code, tools, resources, and utilities
  - See [src/README.md](./src/README.md) for detailed information

- **infra/**: CDK infrastructure code
  - Split stack architecture for services and application
  - See [infra/README.md](./infra/README.md) for detailed deployment instructions

## Additional Resources

- **Creating Test Users**: See [src/README.md](./src/README.md#creating-test-users)
- **Token Management**: See [src/README.md](./src/README.md#obtaining-jwt-tokens)
- **Environment Variables**: See [src/README.md](./src/README.md#environment-variables)
- **Deployment Options**: See [infra/README.md](./infra/README.md#deployment)
- **Troubleshooting**: See [src/README.md](./src/README.md#troubleshooting)
