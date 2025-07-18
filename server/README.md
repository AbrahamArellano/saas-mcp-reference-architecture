# MCP Server

This directory contains the Model Context Protocol (MCP) server implementation that can be deployed to Amazon ECS. The server provides a set of tools and resources for a B2B Travel booking agent.

## Overview

The MCP server is built using:
- Node.js with Express
- AWS SDK for DynamoDB, S3, and STS
- MCP SDK for implementing the Model Context Protocol
- JWT for authentication

## Directory Structure

- `index.js` - Main entry point for the application
- `mcp-server.js` - MCP server implementation
- `resources/` - MCP resources implementation
- `tools/` - MCP tools implementation
- `services/` - Internal services
- `types/` - TypeScript type definitions
- `scripts/` - Utility scripts for development and deployment

## Prerequisites

- Node.js 18+ (server uses Node.js 22 in production)
- AWS CLI configured with appropriate permissions
- Docker or Finch for container operations
- An AWS account with access to ECR

## Local Development

The infrastructure is now split into two stacks to facilitate local development:

1. **Deploy MCP Server Services Stack First**:
   ```bash
   cd ../infra
   ./deploy.sh --services-only
   ```
   This will create the MCPServerTravelBookings DynamoDB table, S3 bucket, and IAM roles.

2. **Configure Local Environment**:
   After deploying the services stack, you'll get outputs for the resource names and ARNs.
   Create a `.env` file with these values:
   ```
   TABLE_NAME=MCPServerTravelBookings
   BUCKET_NAME=<bucket-name-from-stack-output>
   ROLE_ARN=<dynamodb-access-role-arn-from-stack-output>
   ```

3. **Develop and Test Locally**:
   ```bash
   npm install
   npm start
   ```
   Your local MCP Server will now connect to the actual AWS resources.

4. **Build and Push Container**:
   When you're ready to deploy to the cloud:
   ```bash
   ./scripts/pushDockerImage.sh
   ```
   This will build and push the MCP Server container to the `mcp-server-on-ecs` ECR repository.

5. **Deploy MCP Server Application Stack**:
   ```bash
   cd ../infra
   ./deploy.sh --application-only --certificate <your-certificate-arn>
   ```

This workflow ensures consistency between your local development environment and the deployed MCP Server application, as both use the same AWS resources.

## Authentication

The server uses JWT tokens for authentication. You can generate a test token using:

```bash
node scripts/createToken.js
```

This will output a token that can be used for testing the API.

## Building and Pushing the Container Image

The repository includes a script for building and pushing the container image:

```bash
./scripts/pushDockerImage.sh
```

This script:
1. Checks if the ECR repository exists and asks for confirmation to use it
2. Detects whether Docker or Finch is available on your system
3. If both are available, prompts you to choose which tool to use
4. Increments the package version
5. Creates an ECR repository if it doesn't exist
6. Logs in to your AWS ECR repository
7. Builds the container image for linux/amd64 platform
8. Pushes the image to ECR

The script automatically adapts to your environment, making it easy to use regardless of whether you have Docker or Finch installed.

## Environment Variables

The server uses the following environment variables:

- `TABLE_NAME`: Name of the DynamoDB table for storing travel bookings
- `BUCKET_NAME`: Name of the S3 bucket for storing travel policy documents
- `ROLE_ARN`: ARN of the IAM role for accessing DynamoDB with tenant isolation

## API Endpoints

- `/health`: Health check endpoint
- `/mcp`: MCP server endpoint (main API)

## Testing

You can test the server using the generated JWT token:

```bash
curl -X GET http://localhost:3000/health -H "Authorization: Bearer <your-token>"
```

## Deployment

After building and pushing the Docker image, you can deploy the server using the CDK stack in the `infra` directory. See the [infrastructure README](../infra/README.md) for details.

## Security Considerations

- The server implements tenant isolation using STS session tagging
- JWT tokens are used for authentication
- DynamoDB access is restricted by tenant ID using the `LeadingKeys` condition

## Troubleshooting

- If you encounter permission issues, ensure your AWS credentials have the necessary permissions for ECR, DynamoDB, and S3
- Check the server logs for detailed error messages
- Verify that the environment variables are correctly set
