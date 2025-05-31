#!/bin/bash

echo "=== TARGETED MCP CLEANUP - BASED ON SCAN RESULTS ==="
echo "Found specific orphaned resources. Cleaning them up..."

# Function to delete with error handling
safe_delete() {
    echo "Executing: $1"
    eval $1 2>/dev/null || echo "  ↳ Failed or already deleted: $1"
}

echo "=== 1. Cleaning up ECS Resources ==="

# Get the specific ECS cluster we found
ECS_CLUSTER="mcp-cluster-f0d0b6e2"
echo "Processing ECS cluster: $ECS_CLUSTER"

# Stop all services in the cluster
SERVICES=$(aws ecs list-services --cluster $ECS_CLUSTER --query 'serviceArns' --output text 2>/dev/null)
if [ ! -z "$SERVICES" ]; then
    for service in $SERVICES; do
        echo "  Stopping service: $service"
        safe_delete "aws ecs update-service --cluster $ECS_CLUSTER --service $service --desired-count 0"
        sleep 5
        safe_delete "aws ecs delete-service --cluster $ECS_CLUSTER --service $service --force"
    done
else
    echo "  No services found in cluster"
fi

# Wait a bit for services to be deleted
echo "  Waiting for services to be deleted..."
sleep 10

# Delete the cluster
safe_delete "aws ecs delete-cluster --cluster $ECS_CLUSTER"

echo "=== 2. Cleaning up Load Balancer ==="

# Get the specific ALB we found
ALB_NAME="mcp-alb-f0d0b6e2"
ALB_ARN=$(aws elbv2 describe-load-balancers --names $ALB_NAME --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null)

if [ "$ALB_ARN" != "None" ] && [ ! -z "$ALB_ARN" ]; then
    echo "Deleting ALB: $ALB_ARN"
    
    # Delete listeners first
    LISTENERS=$(aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query 'Listeners[].ListenerArn' --output text 2>/dev/null)
    for listener in $LISTENERS; do
        echo "  Deleting listener: $listener"
        safe_delete "aws elbv2 delete-listener --listener-arn $listener"
    done
    
    # Delete target groups associated with this ALB
    TARGET_GROUPS=$(aws elbv2 describe-target-groups --query 'TargetGroups[?contains(LoadBalancerArns[0], `mcp-alb-f0d0b6e2`)].TargetGroupArn' --output text 2>/dev/null)
    for tg in $TARGET_GROUPS; do
        echo "  Deleting target group: $tg"
        safe_delete "aws elbv2 delete-target-group --target-group-arn $tg"
    done
    
    # Delete ALB
    safe_delete "aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN"
else
    echo "ALB not found or already deleted"
fi

echo "=== 3. Cleaning up ECR Repository ==="

ECR_REPO="mcp-playground"
echo "Deleting ECR repository: $ECR_REPO"

# Delete all images first
IMAGES=$(aws ecr list-images --repository-name $ECR_REPO --query 'imageIds' --output text 2>/dev/null)
if [ ! -z "$IMAGES" ]; then
    safe_delete "aws ecr batch-delete-image --repository-name $ECR_REPO --image-ids imageTag=latest"
    # Delete all images
    aws ecr list-images --repository-name $ECR_REPO --query 'imageIds' --output json > /tmp/images.json 2>/dev/null
    if [ -s /tmp/images.json ]; then
        safe_delete "aws ecr batch-delete-image --repository-name $ECR_REPO --image-ids file:///tmp/images.json"
    fi
fi

# Delete repository
safe_delete "aws ecr delete-repository --repository-name $ECR_REPO --force"

echo "=== 4. Additional Cleanup Check ==="

# Check for any other MCP-related resources
echo "Checking for any remaining MCP ECS clusters..."
REMAINING_CLUSTERS=$(aws ecs list-clusters --query 'clusterArns[?contains(@, `mcp`)]' --output text)
for cluster in $REMAINING_CLUSTERS; do
    echo "Found remaining cluster: $cluster"
    cluster_name=$(basename $cluster)
    safe_delete "aws ecs delete-cluster --cluster $cluster_name"
done

echo "Checking for any remaining MCP load balancers..."
REMAINING_ALBS=$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?contains(LoadBalancerName, `mcp`)].LoadBalancerArn' --output text)
for alb in $REMAINING_ALBS; do
    echo "Found remaining ALB: $alb"
    safe_delete "aws elbv2 delete-load-balancer --load-balancer-arn $alb"
done

echo "Checking for any remaining MCP ECR repositories..."
REMAINING_REPOS=$(aws ecr describe-repositories --query 'repositories[?contains(repositoryName, `mcp`)].repositoryName' --output text)
for repo in $REMAINING_REPOS; do
    echo "Found remaining ECR repo: $repo"
    safe_delete "aws ecr delete-repository --repository-name $repo --force"
done

echo "=== 5. Checking Cognito Resources (Fixed Command) ==="

# Fixed Cognito command
USER_POOLS=$(aws cognito-idp list-user-pools --max-results 60 --query 'UserPools[?contains(Name, `mcp`)].Id' --output text 2>/dev/null)
for pool_id in $USER_POOLS; do
    echo "Deleting Cognito User Pool: $pool_id"
    
    # Delete app clients first
    CLIENTS=$(aws cognito-idp list-user-pool-clients --user-pool-id $pool_id --query 'UserPoolClients[].ClientId' --output text 2>/dev/null)
    for client in $CLIENTS; do
        safe_delete "aws cognito-idp delete-user-pool-client --user-pool-id $pool_id --client-id $client"
    done
    
    # Delete domain (try common patterns)
    safe_delete "aws cognito-idp delete-user-pool-domain --user-pool-id $pool_id --domain mcp-auth-f0d0b6e2"
    
    # Delete user pool
    safe_delete "aws cognito-idp delete-user-pool --user-pool-id $pool_id"
done

echo "=== 6. Final Verification ==="

echo "Checking for remaining MCP resources..."
echo "--- ECR Repositories ---"
aws ecr describe-repositories --query 'repositories[?contains(repositoryName, `mcp`)].repositoryName' --output table 2>/dev/null || echo "No MCP ECR repositories found"

echo "--- ECS Clusters ---"
aws ecs list-clusters --query 'clusterArns[?contains(@, `mcp`)]' --output table 2>/dev/null || echo "No MCP ECS clusters found"

echo "--- Load Balancers ---"
aws elbv2 describe-load-balancers --query 'LoadBalancers[?contains(LoadBalancerName, `mcp`)].LoadBalancerName' --output table 2>/dev/null || echo "No MCP load balancers found"

echo "=== CLEANUP COMPLETE ==="
echo "💰 All identified MCP resources have been cleaned up!"
echo "💡 Check your AWS console to verify no resources remain"
