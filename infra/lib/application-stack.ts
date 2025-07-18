import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as ecsPatterns from "aws-cdk-lib/aws-ecs-patterns";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface ApplicationStackProps extends cdk.StackProps {
  // Resources from the ServicesStack
  mcpServerTravelBookingsTable: dynamodb.Table;
  mcpServerPolicyBucket: s3.Bucket;
  mcpServerTaskRole: iam.Role;
  mcpServerDynamoDbAccessRole: iam.Role;
}

export class ApplicationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ApplicationStackProps) {
    super(scope, id, props);

    // Define the repository name
    const repositoryName = process.env.ECR_REPOSITORY_NAME || "mcp-server-on-ecs";
    
    // Use existing repository - we assume it's already created by the server script
    const repository = ecr.Repository.fromRepositoryName(
      this,
      'MCPServerEcrRepository',
      repositoryName
    );

    // Use the image tag from environment variable or default to 'latest'
    const imageTag = process.env.IMAGE_TAG || 'latest';

    // Create the ECS service with ALB
    const mcpServerService = new ecsPatterns.ApplicationLoadBalancedFargateService(
      this,
      "MCPServerFargateService",
      {
        memoryLimitMiB: 1024,
        taskImageOptions: {
          image: ecs.ContainerImage.fromEcrRepository(repository, imageTag),
          environment: {
            TABLE_NAME: props.mcpServerTravelBookingsTable.tableName,
            ROLE_ARN: props.mcpServerDynamoDbAccessRole.roleArn,
            BUCKET_NAME: props.mcpServerPolicyBucket.bucketName,
          },
          containerPort: 3000,
          taskRole: props.mcpServerTaskRole,
        },
        desiredCount: 2,
        minHealthyPercent: 100,
        publicLoadBalancer: true,
        loadBalancerName: "MCPServer", // Set a specific name prefix for the ALB
      }
    );

    // Add HTTPS listener if certificate ARN is provided
    if (!!process.env.CERTIFICATE_ARN)
      mcpServerService.loadBalancer.addListener("MCPServerHttpsListener", {
        port: 443,
        defaultTargetGroups: [mcpServerService.targetGroup],
        certificates: [
          {
            certificateArn: process.env.CERTIFICATE_ARN,
          },
        ],
      });
    else console.log("CERTIFICATE_ARN is not set, not adding HTTPS listener.");

    // Configure health check
    mcpServerService.targetGroup.configureHealthCheck({
      path: "/health",
      port: "3000",
    });
    
    // Output the ALB DNS name
    new cdk.CfnOutput(this, 'MCPServerLoadBalancerDns', {
      value: mcpServerService.loadBalancer.loadBalancerDnsName,
      description: 'The DNS name of the MCP Server load balancer',
      exportName: 'MCPServerLoadBalancerDns',
    });

    // Output the service URL
    new cdk.CfnOutput(this, 'MCPServerServiceURL', {
      value: `http${process.env.CERTIFICATE_ARN ? 's' : ''}://${mcpServerService.loadBalancer.loadBalancerDnsName}`,
      description: 'The URL of the MCP Server service',
      exportName: 'MCPServerServiceURL',
    });
  }
}
