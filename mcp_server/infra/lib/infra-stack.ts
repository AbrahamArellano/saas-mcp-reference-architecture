import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as ecsPatterns from "aws-cdk-lib/aws-ecs-patterns";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Define the repository name
    const repositoryName = process.env.ECR_REPOSITORY_NAME || "stateless-mcp-on-ecs";
    
    // Use existing repository - we assume it's already created by the server script
    const repository = ecr.Repository.fromRepositoryName(
      this,
      'ExistingEcrRepository',
      repositoryName
    );

    const taskRole = new iam.Role(this, "TaskRole", {
      assumedBy: iam.ServicePrincipal.fromStaticServicePrincipleName(
        "ecs-tasks.amazonaws.com"
      ),
    });

    const travelBookingsTable = new dynamodb.Table(this, "TravelBookings", {
      tableName: "TravelBookings",
      partitionKey: { name: "PK", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "SK", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Table will be deleted when stack is destroyed
    });

    const dynamoDbAccessRole = new iam.Role(this, "DynamoDbAccessRole", {
      assumedBy: taskRole,
      description: "Role for DynamoDB row-level access",
    });

    const bucket = new s3.Bucket(this, "TravelPolicyBucket", {
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Bucket will be deleted when stack is destroyed
    });
    bucket.grantRead(taskRole);

    // Optional: Add more granular permissions if needed
    dynamoDbAccessRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
        ],
        resources: [travelBookingsTable.tableArn],
        conditions: {
          "ForAllValues:StringEquals": {
            "dynamodb:LeadingKeys": ["${aws:PrincipalTag/tenantId}"],
          },
        },
      })
    );

    if (!process.env.ADMIN_ROLE_NAME) {
      console.log("ADMIN_ROLE_NAME is not set, not adding to access role.");
    }

    const principals = !!process.env.ADMIN_ROLE_NAME
      ? [
          iam.Role.fromRoleName(this, "AdminRole", process.env.ADMIN_ROLE_NAME),
          taskRole,
        ]
      : [taskRole];

    dynamoDbAccessRole.assumeRolePolicy?.addStatements(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        principals: principals,
        actions: ["sts:TagSession"],
        conditions: { StringLike: { "aws:RequestTag/tenantId": "*" } },
      }),
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        principals: principals,
        actions: ["sts:AssumeRole"],
      })
    );

    // Use the image tag from environment variable or default to 'latest'
    const imageTag = process.env.IMAGE_TAG || 'latest';

    const service = new ecsPatterns.ApplicationLoadBalancedFargateService(
      this,
      "McpServerService",
      {
        // cluster,
        memoryLimitMiB: 1024,
        taskImageOptions: {
          image: ecs.ContainerImage.fromEcrRepository(repository, imageTag),
          environment: {
            TABLE_NAME: travelBookingsTable.tableName,
            ROLE_ARN: dynamoDbAccessRole.roleArn,
            BUCKET_NAME: bucket.bucketName,
          },
          containerPort: 3000,
          taskRole: taskRole,
        },

        desiredCount: 2,
        minHealthyPercent: 100,
        publicLoadBalancer: true,
      }
    );

    if (!!process.env.CERTIFICATE_ARN)
      service.loadBalancer.addListener("HttpsListener", {
        port: 443,
        defaultTargetGroups: [service.targetGroup],
        certificates: [
          {
            certificateArn: process.env.CERTIFICATE_ARN,
          },
        ],
      });
    else console.log("CERTIFICATE_ARN is not set, not adding HTTPS listener.");

    service.targetGroup.configureHealthCheck({
      path: "/health",
      port: "3000",
    });
    
    // Output the ALB DNS name
    new cdk.CfnOutput(this, 'LoadBalancerDns', {
      value: service.loadBalancer.loadBalancerDnsName,
      description: 'The DNS name of the load balancer',
    });
  }
}
