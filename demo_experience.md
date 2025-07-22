# MCP Server Demo Experience [WORK IN PROGRESS]

This document outlines the step-by-step demo flow for the MCP Server reference architecture, showcasing multi-tenant authentication, authorization, and tool access control.

## 1. Deploy the Server End-to-End

Follow these instructions to deploy the complete MCP server infrastructure:

```bash
# Clone the repository (if not already done)
git clone https://github.com/aws-samples/saas-mcp-reference-architecture.git
cd saas-mcp-reference-architecture

# Deploy the services stack first
cd mcp_server/infra
./deploy.sh --services-only

# Build and push the Docker image
cd ../src
./scripts/buildDockerImage.sh  # Build only
./scripts/pushDockerImage.sh   # Build and push to ECR

# Deploy the application stack
cd ../infra
./deploy.sh --application-only
```

After deployment completes, note the outputs from CloudFormation, especially:
- Cognito User Pool ID
- Cognito User Pool Client ID
- Cognito Hosted UI URL
- MCP Server API endpoint

## 2. User Registration and Post-Confirmation Lambda

This step demonstrates the automatic tenant assignment during user registration:

### Create a User from Cognito UI

1. Navigate to the Cognito Hosted UI URL from the CloudFormation outputs
2. Click "Sign up" to create a new account
3. Fill in the required information:
   - Username: `demo-user`
   - Email: Use a valid email you can access
   - Password: Create a strong password following the requirements

### Check User in AWS Console

1. Log in to the AWS Management Console
2. Navigate to Amazon Cognito > User Pools
3. Select the MCP Server User Pool
4. Find and select the user you just created
5. Note that the user doesn't have any custom attributes yet
6. The user status should be "UNCONFIRMED"

### Confirm User Registration

1. Check your email for the verification code
2. Enter the verification code in the Cognito UI to confirm your account
3. After confirmation, you should be redirected to the callback URL (which may show an error, but that's expected)

### Verify Tenant Assignment

1. Return to the AWS Console and refresh the user details
2. The user status should now be "CONFIRMED"
3. Scroll down to see the custom attributes section
4. Verify that the following attributes have been added:
   - `custom:tenantId`: A unique tenant ID (e.g., USER_ABCDEFG_123456)
   - `custom:tenantTier`: The default tier (e.g., "basic")

This demonstrates that the post-confirmation Lambda function successfully assigned tenant information to the user.

## 3. Create Authentication Tokens

Now we'll create both signed and unsigned tokens for testing:

### Create a Signed Token from Cognito

```bash
# Get an authentication token using admin-initiate-auth
export USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name MCPServerServicesStack --query "Stacks[0].Outputs[?OutputKey=='MCPServerUserPoolId'].OutputValue" --output text)
export CLIENT_ID=$(aws cloudformation describe-stacks --stack-name MCPServerServicesStack --query "Stacks[0].Outputs[?OutputKey=='MCPServerUserPoolClientId'].OutputValue" --output text)

# Replace with your username and password
aws cognito-idp admin-initiate-auth \
  --user-pool-id $USER_POOL_ID \
  --client-id $CLIENT_ID \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=demo-user,PASSWORD=YourPassword123!

# Save the IdToken from the output
export SIGNED_TOKEN="eyJraWQiOiJ..."  # Replace with your actual token
```

### Create an Unsigned Token

```bash
# Use the createToken.js script to create an unsigned token
cd /home/sagemaker-user/saas-mcp-reference-architecture/mcp_server/src
node scripts/createToken.js demo-user

# Save the output token
export UNSIGNED_TOKEN="eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0..."  # Replace with the actual output
```

## 4. Test the Tokens with MCP Server

Now we'll test both tokens to demonstrate the different behavior:

### Get the MCP Server Endpoint

```bash
export MCP_ENDPOINT=$(aws cloudformation describe-stacks --stack-name MCPServerApplicationStack --query "Stacks[0].Outputs[?OutputKey=='MCPServerApiEndpoint'].OutputValue" --output text)
```

### Test with Signed Token

```bash
# List available tools with signed token
curl -X POST $MCP_ENDPOINT/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $SIGNED_TOKEN" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'

# Expected output: All tools are available (whoami, list_bookings, find_flights, etc.)
```

### Test with Unsigned Token

```bash
# List available tools with unsigned token
curl -X POST $MCP_ENDPOINT/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $UNSIGNED_TOKEN" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'

# Expected output: Only the whoami tool is available
```

### Test the whoami Tool with Both Tokens

```bash
# Test whoami with signed token (NOT WORKING --> need to use a proper client)
curl -X POST $MCP_ENDPOINT/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $SIGNED_TOKEN" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}}'

# Expected output: User information with authenticated: true

# Test whoami with unsigned token (NOT WORKING --> need to use a proper client)
curl -X POST $MCP_ENDPOINT/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $UNSIGNED_TOKEN" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}}'

# Expected output: User information with authenticated: false
```

### Test Other Tools with Unsigned Token

```bash
# Try to access list_bookings with unsigned token (NOT WORKING --> need to use a client)
curl -X POST $MCP_ENDPOINT/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $UNSIGNED_TOKEN" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_bookings", "arguments": {}}}'

# Expected output: Authentication error - unauthorized access
```

## Summary

This demo showcases:

1. **Multi-tenant Authentication**: Users are automatically assigned to tenants during registration
2. **Token-based Authorization**: Different tokens provide different levels of access
3. **Public vs. Protected Tools**: The whoami tool is accessible with any token, while other tools require proper authentication
4. **User Information**: The whoami tool provides detailed information about the token and authentication status

The MCP server architecture demonstrates a secure, multi-tenant approach to building SaaS applications with AWS services, leveraging Cognito for authentication and custom attributes for tenant isolation.
