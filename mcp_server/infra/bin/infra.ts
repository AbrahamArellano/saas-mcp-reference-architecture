#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { ServicesStack } from '../lib/services-stack';
import { ApplicationStack } from '../lib/application-stack';

const app = new cdk.App();

// Define the environment for both stacks
const env = { 
  account: process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID, 
  region: process.env.CDK_DEFAULT_REGION || process.env.AWS_REGION || 'us-east-1'
};

// Create the services stack first
const mcpServerServicesStack = new ServicesStack(app, 'MCPServerServicesStack', {
  /* Use the same environment for both stacks */
  env: env
});

// Create the application stack, passing in the resources from the services stack
const mcpServerApplicationStack = new ApplicationStack(app, 'MCPServerApplicationStack', {
  mcpServerTravelBookingsTable: mcpServerServicesStack.mcpServerTravelBookingsTable,
  mcpServerPolicyBucket: mcpServerServicesStack.mcpServerPolicyBucket,
  mcpServerTaskRole: mcpServerServicesStack.mcpServerTaskRole,
  mcpServerDynamoDbAccessRole: mcpServerServicesStack.mcpServerDynamoDbAccessRole,
  mcpServerUserPool: mcpServerServicesStack.mcpServerUserPool,
  mcpServerUserPoolClient: mcpServerServicesStack.mcpServerUserPoolClient,
  mcpServerUserPoolDomain: mcpServerServicesStack.mcpServerUserPoolDomain,
  
  /* Use the same environment as the services stack */
  env: env
});

// Add a dependency to ensure the services stack is created first
mcpServerApplicationStack.addDependency(mcpServerServicesStack);
