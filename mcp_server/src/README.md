# MCP Server Implementation

This directory contains the source code for the Model Context Protocol (MCP) server implementation. For general information about the MCP server, deployment instructions, and architecture overview, please refer to the [top-level README](../README.md).

## Directory Structure

- `index.js` - Main entry point for the application
- `mcp-server.js` - MCP server implementation and tool registration
- `jwt-verifier.js` - JWT verification module with Cognito integration
- `transport.js` - HTTP transport layer with authentication
- `resources/` - MCP resources implementation
- `tools/` - MCP tools implementation
- `services/` - Internal services
- `types/` - TypeScript type definitions
- `scripts/` - Utility scripts for development and deployment

## Implementation Details

### Authentication Flow

1. Client sends request with `Authorization: Bearer <token>` header
2. `transport.js` extracts the token and passes it to `jwt-verifier.js`
3. `jwt-verifier.js` verifies the token using Cognito's JWKS endpoint
4. User and tenant information is extracted from the token
5. Request is processed with the authenticated user context

### Multi-Tenant Implementation

- **Tenant Identification**: Custom claims in JWT tokens (`custom:tenantId`, `custom:tenantTier`)
- **Data Isolation**: DynamoDB partition keys prefixed with tenant ID
- **Access Control**: STS session tagging and IAM policies

### Available Tools

The MCP server implements the following tools:

1. `whoami` - Returns information about the current user (works without authentication)
   - This tool is always available, even for unauthenticated users
   - It can be used to check authentication status and token information
   - It accepts both signed and unsigned tokens
   - For unsigned tokens, it will show token information but mark `authenticated: false`
   - For signed tokens verified with Cognito, it will show `authenticated: true`
   - Response includes user info, token details, and environment information
2. `list_bookings` - Get an overview of a user's bookings
3. `find_flights` - Search for available flights
4. `book_flight` - Book a flight
5. `book_hotel` - Book a hotel room
6. `list_hotels` - Search for available hotels
7. `loyalty_info` - Get loyalty program information

### Available Resources

1. `CompanyTravelPolicy` - Access to travel policy documents
2. `CompanyTravelPolicyPerTenant` - Tenant-specific travel policies

## Development

### Local Environment Setup

Create a `.env` file with the following variables:

```
TABLE_NAME=MCPServerTravelBookings
BUCKET_NAME=<bucket-name-from-stack-output>
ROLE_ARN=<dynamodb-access-role-arn-from-stack-output>
COGNITO_USER_POOL_ID=<user-pool-id-from-stack-output>
COGNITO_CLIENT_ID=<client-id-from-stack-output>
AWS_REGION=us-east-1
```

### Running Locally

```bash
npm install
npm start
```

### Docker Image Management

#### Building the Docker Image

```bash
# First, ensure package.json and package-lock.json are in sync
npm install

# Build the Docker image locally
./scripts/buildDockerImage.sh
```

This script:
1. Detects whether Docker or Finch is available on your system
2. Increments the package version
3. Builds the container image for linux/amd64 platform
4. Tags the image with a local tag and ECR URI

#### Building and Pushing to ECR

```bash
# Build and push the Docker image to ECR
./scripts/pushDockerImage.sh
```

This script:
1. Checks if the ECR repository exists and asks for confirmation to use it
2. Creates an ECR repository if it doesn't exist
3. Logs in to your AWS ECR repository
4. Calls buildDockerImage.sh to build the image
5. Pushes the image to ECR

## Authentication Utilities

### Creating Test Users

```bash
# Create a user
aws cognito-idp admin-create-user \
    --user-pool-id <your-user-pool-id> \
    --username testuser1 \
    --user-attributes Name=email,Value=test@example.com \
    --temporary-password TempPass123! \
    --message-action SUPPRESS

# Set custom attributes for multi-tenancy
aws cognito-idp admin-update-user-attributes \
    --user-pool-id <your-user-pool-id> \
    --username testuser1 \
    --user-attributes Name=custom:tenantId,Value=ABC123 Name=custom:tenantTier,Value=premium

# Set permanent password
aws cognito-idp admin-set-user-password \
    --user-pool-id <your-user-pool-id> \
    --username testuser1 \
    --password SecurePass123! \
    --permanent
```

### Using the createCognitoToken.js Script

The `createCognitoToken.js` script generates Cognito-compatible JWT tokens for testing purposes:

```bash
# Generate a token with default test values
node scripts/createCognitoToken.js

# Generate a token for a specific Cognito user
node scripts/createCognitoToken.js username1
```

For detailed information about token generation and usage, see the [top-level README](../README.md#authentication).

## Troubleshooting

### Authentication Issues

- **"COGNITO_USER_POOL_ID environment variable is required"**: Ensure CDK deployment completed successfully
- **"JWT verification failed: invalid signature"**: Token may be expired or from wrong User Pool
- **"Error getting signing key"**: Check network connectivity to Cognito JWKS endpoint

### Development Issues

- **Permission errors**: Ensure AWS credentials have necessary permissions
- **Token generation**: Use appropriate script for your environment (signed vs unsigned tokens)
- **Environment variables**: Verify all required variables are set correctly

### Debug Mode

Enable detailed logging:
```bash
# In your .env file
LOG_LEVEL=debug
```
