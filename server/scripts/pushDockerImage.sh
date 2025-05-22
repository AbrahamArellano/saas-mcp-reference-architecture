#!/bin/bash
export ECR_REPO=stateless-mcp-on-ecs
export ECR_IMAGE_TAG=latest
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
export ECR_REPO_URI=$AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/$ECR_REPO:$ECR_IMAGE_TAG

echo Logging in...
aws ecr get-login-password --region us-east-1 | finch login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

echo Incrementing app version...
# cd src/js/mcpserver
npm version patch

echo $ECR_REPO_URI

echo Building image and publishing to private ECR...
aws ecr create-repository --repository-name $ECR_REPO --no-cli-pager
finch build --platform linux/amd64 --provenance=false -t $ECR_REPO_URI .
finch push $ECR_REPO_URI --platform linux/amd64

echo All done!