#!/bin/bash

export CDK_DEFAULT_ACCOUNT=<your-account> # e.g. "123456789012"
export CDK_DEFAULT_REGION=<your-region> # e.g. "us-east-1"
export CDK_QUALIFIER=<your-qualifier> # e.g. "dev" or "prod"

# Domain configuration
export CERTIFICATE_ARN=<your-arn> # e.g. "arn:aws:acm:us-east-1:123456789012:certificate/1234ab1a-1234-1ab2-aa1b-01aa23b4c567"
export HOSTED_ZONE_ID=<your-zone-id> # e.g. "/hostedzone/A12345678AB9C0DE1FGHI"
export ZONE_NAME=<your-domain> # e.g. "example.com"
export RECORD_NAME_MCP=<your-subdomain> # e.g. "mcp.example.com"

# Optional: CloudFront prefix list for security group
export CLOUDFRONT_PREFIX_LIST_ID=<your-list> # e.g. "pl-3b927c52" for us-east-1
