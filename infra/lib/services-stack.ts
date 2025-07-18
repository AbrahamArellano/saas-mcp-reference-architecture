import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface ServicesStackProps extends cdk.StackProps {
  // Optional props that can be passed from the parent stack
}

export class ServicesStack extends cdk.Stack {
  // Export these resources to be used by the ApplicationStack
  public readonly mcpServerTravelBookingsTable: dynamodb.Table;
  public readonly mcpServerPolicyBucket: s3.Bucket;
  public readonly mcpServerTaskRole: iam.Role;
  public readonly mcpServerDynamoDbAccessRole: iam.Role;

  constructor(scope: Construct, id: string, props?: ServicesStackProps) {
    super(scope, id, props);

    // Create the task role for ECS
    this.mcpServerTaskRole = new iam.Role(this, "MCPServerTaskRole", {
      assumedBy: iam.ServicePrincipal.fromStaticServicePrincipleName(
        "ecs-tasks.amazonaws.com"
      ),
    });

    // Create the DynamoDB table
    this.mcpServerTravelBookingsTable = new dynamodb.Table(this, "MCPServerTravelBookings", {
      tableName: "MCPServerTravelBookings",
      partitionKey: { name: "PK", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "SK", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Table will be deleted when stack is destroyed
    });

    // Create the DynamoDB access role
    this.mcpServerDynamoDbAccessRole = new iam.Role(this, "MCPServerDynamoDbAccessRole", {
      assumedBy: this.mcpServerTaskRole,
      description: "Role for DynamoDB row-level access for MCP Server",
    });

    // Create the S3 bucket
    this.mcpServerPolicyBucket = new s3.Bucket(this, "MCPServerTravelPolicyBucket", {
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Bucket will be deleted when stack is destroyed
    });
    this.mcpServerPolicyBucket.grantRead(this.mcpServerTaskRole);

    // Add permissions to the DynamoDB access role
    this.mcpServerDynamoDbAccessRole.addToPolicy(
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
        resources: [this.mcpServerTravelBookingsTable.tableArn],
        conditions: {
          "ForAllValues:StringEquals": {
            "dynamodb:LeadingKeys": ["${aws:PrincipalTag/tenantId}"],
          },
        },
      })
    );

    // Handle admin role if provided
    if (!process.env.ADMIN_ROLE_NAME) {
      console.log("ADMIN_ROLE_NAME is not set, not adding to access role.");
    }

    const principals = !!process.env.ADMIN_ROLE_NAME
      ? [
          iam.Role.fromRoleName(this, "MCPServerAdminRole", process.env.ADMIN_ROLE_NAME),
          this.mcpServerTaskRole,
        ]
      : [this.mcpServerTaskRole];

    this.mcpServerDynamoDbAccessRole.assumeRolePolicy?.addStatements(
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

    // Output the resource ARNs and names
    new cdk.CfnOutput(this, 'MCPServerDynamoDBTableName', {
      value: this.mcpServerTravelBookingsTable.tableName,
      description: 'The name of the MCP Server DynamoDB table',
      exportName: 'MCPServerTravelBookingsTableName',
    });

    new cdk.CfnOutput(this, 'MCPServerPolicyBucketName', {
      value: this.mcpServerPolicyBucket.bucketName,
      description: 'The name of the MCP Server policy S3 bucket',
      exportName: 'MCPServerTravelPolicyBucketName',
    });

    new cdk.CfnOutput(this, 'MCPServerTaskRoleArn', {
      value: this.mcpServerTaskRole.roleArn,
      description: 'The ARN of the MCP Server task role',
      exportName: 'MCPServerTaskRoleArn',
    });

    new cdk.CfnOutput(this, 'MCPServerDynamoDbAccessRoleArn', {
      value: this.mcpServerDynamoDbAccessRole.roleArn,
      description: 'The ARN of the MCP Server DynamoDB access role',
      exportName: 'MCPServerDynamoDbAccessRoleArn',
    });
  }
}
