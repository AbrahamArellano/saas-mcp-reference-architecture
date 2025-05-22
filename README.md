# MCP ISV Hackathon Prototype

This repository contains an MCP server using the Streamable HTTP transport written with the Typescript SDK, that can be deployed to Amazon ECS. The repository also contains two client implementations that leverage Streamlit and communicate with Amazon Bedrock, support remote MCP servers and can be hosted on AWS.

> [CAUTION]
> Not all components have been merged or cleaned yet. We will provide the updated and infrastructure as code in the next couple of days.

## Overall architecture

![Architecture Overview](/resources/mcp_hackathon.png)

## Live demos and related resources

1. [Remote MCP Server for a B2B Travel booking agent](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/25f60b0412d3e7e55b33eb6207b3177136b7a07db9fe90be025fd4302e2a897b) 
2. Bedrock powered MCP clients with UI hosted on AWS + CLI with remote server support ([Live Demo Client 1](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/b431ce7582b2ff212adc04b66bcb9f9adc3aeef638c29a2d60e69e56b6cbfc9e) / [Client 2](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/4e0f90886d542843bc95313204f40ba5879a17078eaed2544e1ce8f378f02ee6) / [Python Client](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/9c61d036d576a9ec4a30be0b80d7af96fff8f80a9c3fd2a9f920fea22b5f0a28))
3. [Business narrative for internal and customer facing MCP/Agent enablement](https://quip-amazon.com/wjUNA49v3guV/MCP-Business-Working-Group)
4. [MCP enablement session run by AWS Anthropic SA @nsmagt](https://broadcast.amazon.com/videos/1538819)

## Structure

- The `infra` folder contains a CDK project that deploys the application to ECS. The stack deploys a load-balanced Fargate service running the server behind an ALB (supplied with a **preexisting certificate**). 

  The application data is stored in a DynamoDB table and an S3 bucket for policy document storage. We showcase tenant-isolation capabilities using STS session tagging and the `leadingKeys` condition.
  
  > [!CAUTION]
  > The stack expects an existing TLS certificate as well as an existing container image. You will also need to add the DNS records by hand.

- The `server` folder contains the MCP server. The `resources` and `tools` folders contain their MCP counterparts, while `services` and `types` contain project-internal code. Authentication can be found in `index.js` and the registration of tools and resources in `mcp-server.js`.

  The `scripts/` directory contain some handy scripts for development:
    - `pushDockerImage.sh` builds and pushes the container image to a private ECR using your default credentials. Because of the company policy against Docker Desktop, it is currently using finch.
    - `createToken.js` can be used to create JWTs for testing.

## Testing with Claude Desktop

This project is deployed under https://mcp.fredscho.people.aws.dev. If you want to test the project using Claude Destop, use the following configuration:

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