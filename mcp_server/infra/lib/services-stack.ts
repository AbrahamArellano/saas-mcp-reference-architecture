import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as path from "path";
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
  public readonly mcpServerUserPool: cognito.UserPool;
  public readonly mcpServerUserPoolClient: cognito.UserPoolClient;
  public readonly mcpServerUserPoolDomain: cognito.UserPoolDomain;
  public readonly postConfirmationLambda: lambda.Function;

  constructor(scope: Construct, id: string, props?: ServicesStackProps) {
    super(scope, id, props);

    // Create the task role for ECS
    this.mcpServerTaskRole = new iam.Role(this, "MCPServerTaskRole", {
      assumedBy: iam.ServicePrincipal.fromStaticServicePrincipleName(
        "ecs-tasks.amazonaws.com"
      ),
    });

    // Create Lambda function for post-confirmation tenant assignment
    this.postConfirmationLambda = new lambda.Function(this, "PostConfirmationLambda", {
      runtime: lambda.Runtime.NODEJS_20_X,
      handler: "post-confirmation-handler.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "../lambda")),
      timeout: cdk.Duration.seconds(30),
      description: "Assigns tenant information to users after email confirmation",
    });

    // Grant Lambda permission to update Cognito user attributes
    this.postConfirmationLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "cognito-idp:AdminUpdateUserAttributes",
          "cognito-idp:AdminGetUser",
        ],
        resources: ["*"], // Will be restricted to specific User Pool after creation
      })
    );

    // Create Cognito User Pool for authentication
    this.mcpServerUserPool = new cognito.UserPool(this, "MCPServerUserPool", {
      userPoolName: "mcp-server-users",
      selfSignUpEnabled: true,
      signInAliases: {
        email: true,
        username: true,
      },
      autoVerify: {
        email: true,
      },
      standardAttributes: {
        email: {
          required: true,
          mutable: true,
        },
        givenName: {
          required: false,
          mutable: true,
        },
        familyName: {
          required: false,
          mutable: true,
        },
      },
      customAttributes: {
        tenantId: new cognito.StringAttribute({ 
          mutable: true,
          minLen: 1,
          maxLen: 50,
        }),
        tenantTier: new cognito.StringAttribute({ 
          mutable: true,
          minLen: 1,
          maxLen: 20,
        }),
      },
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      // We'll add the Lambda trigger after creating the Lambda function
    });

    // Now add the Lambda trigger to the User Pool using CloudFormation directly
    const cfnUserPool = this.mcpServerUserPool.node.defaultChild as cognito.CfnUserPool;
    cfnUserPool.lambdaConfig = {
      postConfirmation: this.postConfirmationLambda.functionArn,
    };
    
    // Grant Cognito permission to invoke the Lambda function
    // Use a string concatenation instead of direct reference to break circular dependency
    new lambda.CfnPermission(this, 'CognitoInvokePostConfirmationLambda', {
      action: 'lambda:InvokeFunction',
      functionName: this.postConfirmationLambda.functionName,
      principal: 'cognito-idp.amazonaws.com',
      sourceArn: `arn:aws:cognito-idp:${this.region}:${this.account}:userpool/${this.mcpServerUserPool.userPoolId}`,
    });

    // Create User Pool Client with OAuth settings for Hosted UI
    this.mcpServerUserPoolClient = this.mcpServerUserPool.addClient("MCPServerClient", {
      userPoolClientName: "mcp-server-client",
      authFlows: {
        userPassword: true,
        userSrp: true,
        adminUserPassword: true,
      },
      generateSecret: false, // For simplicity, not using client secret
      accessTokenValidity: cdk.Duration.hours(1),
      idTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
      preventUserExistenceErrors: true,
      // OAuth settings for Hosted UI
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
          implicitCodeGrant: true,
        },
        scopes: [
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls: [
          'http://localhost:3000/callback',
          'https://localhost:3000/callback',
          // Add your production callback URLs here
          // 'https://your-domain.com/callback',
        ],
        logoutUrls: [
          'http://localhost:3000/logout',
          'https://localhost:3000/logout',
          // Add your production logout URLs here
          // 'https://your-domain.com/logout',
        ],
      },
      supportedIdentityProviders: [
        cognito.UserPoolClientIdentityProvider.COGNITO,
      ],
    });

    // Create User Pool Domain for Hosted UI
    this.mcpServerUserPoolDomain = this.mcpServerUserPool.addDomain("MCPServerDomain", {
      cognitoDomain: {
        domainPrefix: `mcp-server-${cdk.Stack.of(this).account}-${Math.random().toString(36).substring(2, 8)}`,
      },
    });

    // We'll use the wildcard permission defined earlier
    // No need to update Lambda permissions again

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

    new cdk.CfnOutput(this, 'MCPServerUserPoolId', {
      value: this.mcpServerUserPool.userPoolId,
      description: 'The ID of the MCP Server Cognito User Pool',
      exportName: 'MCPServerUserPoolId',
    });

    new cdk.CfnOutput(this, 'MCPServerUserPoolClientId', {
      value: this.mcpServerUserPoolClient.userPoolClientId,
      description: 'The ID of the MCP Server Cognito User Pool Client',
      exportName: 'MCPServerUserPoolClientId',
    });

    new cdk.CfnOutput(this, 'MCPServerUserPoolArn', {
      value: this.mcpServerUserPool.userPoolArn,
      description: 'The ARN of the MCP Server Cognito User Pool',
      exportName: 'MCPServerUserPoolArn',
    });

    new cdk.CfnOutput(this, 'MCPServerUserPoolDomain', {
      value: this.mcpServerUserPoolDomain.domainName,
      description: 'The domain name for the MCP Server Cognito Hosted UI',
      exportName: 'MCPServerUserPoolDomain',
    });

    new cdk.CfnOutput(this, 'MCPServerHostedUIUrl', {
      value: `https://${this.mcpServerUserPoolDomain.domainName}.auth.${this.region}.amazoncognito.com`,
      description: 'The full URL for the MCP Server Cognito Hosted UI',
      exportName: 'MCPServerHostedUIUrl',
    });

    new cdk.CfnOutput(this, 'MCPServerLoginUrl', {
      value: `https://${this.mcpServerUserPoolDomain.domainName}.auth.${this.region}.amazoncognito.com/login?client_id=${this.mcpServerUserPoolClient.userPoolClientId}&response_type=code&scope=email+openid+profile&redirect_uri=http://localhost:3000/callback`,
      description: 'Direct login URL for the MCP Server Cognito Hosted UI',
      exportName: 'MCPServerLoginUrl',
    });

    new cdk.CfnOutput(this, 'MCPServerPostConfirmationLambdaArn', {
      value: this.postConfirmationLambda.functionArn,
      description: 'The ARN of the Post-Confirmation Lambda function for tenant assignment',
      exportName: 'MCPServerPostConfirmationLambdaArn',
    });
  }
}
