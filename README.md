# MCP ISV Hackathon Prototype

This repository contains an MCP server using the Streamable HTTP transport written with the Typescript SDK, that can be deployed to Amazon ECS. The repository also contains two client implementations that leverage Streamlit and communicate with Amazon Bedrock, support remote MCP servers and can be hosted on AWS.

## Overall Architecture

![Architecture Overview](/resources/mcp_hackathon.png)

## MCP Server

For detailed information, see the [MCP Server README](./mcp_server/README.md).

The MCP server implementation is organized into two main components:

- **[Server Implementation](./mcp_server/src/)**: Core MCP server code with tools, resources, and authentication
- **[Infrastructure](./mcp_server/infra/)**: CDK project for AWS deployment

### Quick Start

```bash
# Deploy services stack
cd mcp_server/infra
./deploy.sh --services-only

# Build and push Docker image
cd ../src
./scripts/buildDockerImage.sh  # Build only
./scripts/pushDockerImage.sh   # Build and push to ECR

# Deploy application stack
cd ../infra
./deploy.sh --application-only
```

## MCP Client Implementations

This repository includes three different MCP client implementations, each showcasing different approaches to integrating with MCP servers:

### Production-Ready Client with Dynamic Server Management

- [Client README](./mcp_clients/streamlit-client/README.md)

The `mcp_clients/streamlit-client` folder contains a production-ready MCP client with comprehensive features for enterprise deployment:

- **Architecture**: Built with Streamlit frontend and FastAPI backend
- **Security**: AWS Cognito authentication with infrastructure-level security
- **Deployment**: ECS Fargate deployment with Application Load Balancer
- **Features**:
  - Dynamic MCP server management (add/remove at runtime)
  - Enterprise-grade authentication
  - Direct integration with Amazon Bedrock models
  - Professional UI with conversation history

This implementation is ideal for production deployments requiring robust security and user management.

### Lightweight Python Client with Model Integration

The `mcp_clients/lightweight-client` folder contains a lightweight Python implementation that demonstrates direct integration between MCP and language models:

- **Architecture**: Pure Python implementation with HTTP streaming support
- **Features**:
  - Direct integration with language models
  - Streaming support for real-time responses
  - Simple API for tool registration and execution

This implementation is ideal for developers looking to understand the core mechanics of MCP integration with models.

### Strands Agents Integration

- [Strands Agents README](./mcp_clients/strands-agents-client/README.md)

The `mcp_clients/strands-agents-client` folder demonstrates integration between MCP and the Strands Agents framework:

- **Architecture**: Python-based integration between Strands Agents and MCP
- **Features**:
  - Bridging Strands Agents capabilities with MCP tools
  - Simple implementation requiring minimal setup
  - Example of framework interoperability

This implementation requires Python 3.10+ and may require manual installation of the Strands package as described in its README.

## Testing with Claude Desktop

A version of this project is deployed under https://mcp.fredscho.people.aws.dev. If you want to test the project using Claude Desktop, use the following configuration:

> [!CAUTION]
> Make sure to install a reasonably recent version of Node.js.

```json
{
  "mcpServers": {
    "remote-example": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://mcp.fredscho.people.aws.dev/mcp",
        "--header",
        "Authorization: Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJ1c2VyMSIsIm5hbWUiOiJUZXN0IFVzZXIxIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZXMiOlsidXNlciIsImFkbWluIl0sInBlcm1pc3Npb25zIjpbInJlYWQiXSwib3JnIjoidGVuYW50MSIsImN1c3RvbTp0ZW5hbnRJZCI6IkFCQzEyMyIsImlhdCI6MTc0NzEzMTcwMSwiZXhwIjoxNzQ3MTM1MzAxfQ."
      ]
    }
  }
}
```

## Live Demos and Related Resources

1. [Remote MCP Server for a B2B Travel booking agent](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/25f60b0412d3e7e55b33eb6207b3177136b7a07db9fe90be025fd4302e2a897b) 
2. Bedrock powered MCP clients with UI hosted on AWS + CLI with remote server support:
   - [Live Demo Client 1](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/b431ce7582b2ff212adc04b66bcb9f9adc3aeef638c29a2d60e69e56b6cbfc9e)
   - [Client 2](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/4e0f90886d542843bc95313204f40ba5879a17078eaed2544e1ce8f378f02ee6)
   - [Python Client](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/9c61d036d576a9ec4a30be0b80d7af96fff8f80a9c3fd2a9f920fea22b5f0a28)
3. [Business narrative for internal and customer facing MCP/Agent enablement](https://quip-amazon.com/wjUNA49v3guV/MCP-Business-Working-Group)
4. [MCP enablement session run by AWS Anthropic SA @nsmagt](https://broadcast.amazon.com/videos/1538819)
