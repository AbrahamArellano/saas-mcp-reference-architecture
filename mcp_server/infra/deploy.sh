#!/bin/bash

# Default values
SERVICES_STACK_NAME="MCPServerServicesStack"
APPLICATION_STACK_NAME="MCPServerApplicationStack"
CERTIFICATE_ARN="arn:aws:acm:us-east-1:777200923596:certificate/9697ac7e-4703-4ac4-bb8d-07dd45a0a118"
ECR_REPOSITORY_NAME="mcp-server-on-ecs"
IMAGE_TAG="latest"
ADMIN_ROLE_NAME=""
AWS_REGION=${AWS_REGION:-us-east-1}
NO_ROLLBACK="true"  # Changed to true by default
DEPLOY_SERVICES="true"
DEPLOY_APPLICATION="true"

# Display help message
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -h, --help                 Show this help message"
    echo "  --services-stack NAME      Set the services stack name (default: MCPServerServicesStack)"
    echo "  --app-stack NAME           Set the application stack name (default: MCPServerApplicationStack)"
    echo "  -c, --certificate ARN      Set the ACM certificate ARN"
    echo "  -r, --repository NAME      Set the ECR repository name (default: mcp-server-on-ecs)"
    echo "  -t, --image-tag TAG        Set the container image tag (default: latest)"
    echo "  -a, --admin-role NAME      Set the admin role name (optional)"
    echo "  -g, --region REGION        Set the AWS region (default: from AWS_REGION env var or us-east-1)"
    echo "  -n, --no-rollback          Disable rollback on failure (default: true)"
    echo "  --rollback                 Enable rollback on failure"
    echo "  --services-only            Deploy only the services stack"
    echo "  --application-only         Deploy only the application stack"
    echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -h|--help)
            show_help
            exit 0
            ;;
        --services-stack)
            SERVICES_STACK_NAME="$2"
            shift 2
            ;;
        --app-stack)
            APPLICATION_STACK_NAME="$2"
            shift 2
            ;;
        -c|--certificate)
            CERTIFICATE_ARN="$2"
            shift 2
            ;;
        -r|--repository)
            ECR_REPOSITORY_NAME="$2"
            shift 2
            ;;
        -t|--image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -a|--admin-role)
            ADMIN_ROLE_NAME="$2"
            shift 2
            ;;
        -g|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -n|--no-rollback)
            NO_ROLLBACK="true"
            shift
            ;;
        --rollback)
            NO_ROLLBACK="false"
            shift
            ;;
        --services-only)
            DEPLOY_SERVICES="true"
            DEPLOY_APPLICATION="false"
            shift
            ;;
        --application-only)
            DEPLOY_SERVICES="false"
            DEPLOY_APPLICATION="true"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Prompt for certificate ARN if not provided and deploying application stack
if [ "$DEPLOY_APPLICATION" = "true" ] && [ -z "$CERTIFICATE_ARN" ]; then
    echo "No certificate ARN provided."
    read -p "Do you want to deploy with HTTPS (requires an ACM certificate)? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter your ACM certificate ARN: " CERTIFICATE_ARN
        if [ -z "$CERTIFICATE_ARN" ]; then
            echo "Certificate ARN is required for HTTPS. Exiting."
            exit 1
        fi
    else
        echo "Continuing without HTTPS configuration."
    fi
fi

# Check if the ECR repository exists if deploying application stack
if [ "$DEPLOY_APPLICATION" = "true" ]; then
    echo "Checking if ECR repository '$ECR_REPOSITORY_NAME' exists..."
    if ! aws ecr describe-repositories --repository-names "$ECR_REPOSITORY_NAME" --region "$AWS_REGION" &> /dev/null; then
        echo "ERROR: ECR repository '$ECR_REPOSITORY_NAME' does not exist."
        echo "Please run the pushDockerImage.sh script in the mcp_server/src directory first to create the repository and push the image."
        exit 1
    fi
    echo "ECR repository '$ECR_REPOSITORY_NAME' exists. Proceeding with deployment."
fi

# Set environment variables for deployment
export CERTIFICATE_ARN="$CERTIFICATE_ARN"
export ECR_REPOSITORY_NAME="$ECR_REPOSITORY_NAME"
export IMAGE_TAG="$IMAGE_TAG"
export ADMIN_ROLE_NAME="$ADMIN_ROLE_NAME"
export AWS_REGION="$AWS_REGION"

# Deploy the stacks
if [ "$DEPLOY_SERVICES" = "true" ]; then
    echo "Deploying MCP Server services stack '$SERVICES_STACK_NAME' with the following configuration:"
    if [ -n "$ADMIN_ROLE_NAME" ]; then
        echo "  Admin Role: $ADMIN_ROLE_NAME"
    fi
    echo "  AWS Region: $AWS_REGION"
    echo "  No Rollback: $NO_ROLLBACK"
    
    echo "Starting MCP Server services deployment..."
    if [ "$NO_ROLLBACK" = "true" ]; then
        npx cdk deploy "$SERVICES_STACK_NAME" --require-approval never --no-rollback --exclusively
    else
        npx cdk deploy "$SERVICES_STACK_NAME" --require-approval never --exclusively
    fi
    
    # Check if services deployment was successful
    if [ $? -ne 0 ]; then
        echo "MCP Server services deployment failed. Exiting."
        exit 1
    fi
    
    echo "MCP Server services deployment successful!"
fi

if [ "$DEPLOY_APPLICATION" = "true" ]; then
    echo "Deploying MCP Server application stack '$APPLICATION_STACK_NAME' with the following configuration:"
    if [ -n "$CERTIFICATE_ARN" ]; then
        echo "  Certificate ARN: $CERTIFICATE_ARN"
    else
        echo "  HTTPS: Disabled"
    fi
    echo "  ECR Repository: $ECR_REPOSITORY_NAME"
    echo "  Image Tag: $IMAGE_TAG"
    echo "  AWS Region: $AWS_REGION"
    echo "  No Rollback: $NO_ROLLBACK"
    
    echo "Starting MCP Server application deployment..."
    if [ "$NO_ROLLBACK" = "true" ]; then
        npx cdk deploy "$APPLICATION_STACK_NAME" --require-approval never --no-rollback --exclusively
    else
        npx cdk deploy "$APPLICATION_STACK_NAME" --require-approval never --exclusively
    fi
    
    # Check if application deployment was successful
    if [ $? -eq 0 ]; then
        echo "MCP Server application deployment successful!"
        
        # Get the ALB DNS name
        ALB_DNS=$(aws cloudformation describe-stacks --stack-name "$APPLICATION_STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='MCPServerLoadBalancerDns'].OutputValue" --output text)
        
        echo ""
        echo "MCP Server Load Balancer DNS: $ALB_DNS"
        echo ""
        echo "Next steps:"
        echo "1. Set up DNS records pointing to the ALB"
        echo "2. Test your MCP Server at http${CERTIFICATE_ARN:+s}://<your-domain>/mcp"
    else
        echo "MCP Server application deployment failed. Check the CloudFormation events for more information."
        exit 1
    fi
fi
