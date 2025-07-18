#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

class BootstrapStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    
    // This is an empty stack just to test deployment
    new cdk.CfnOutput(this, 'TestOutput', {
      value: 'Test successful',
    });
  }
}

const app = new cdk.App();
new BootstrapStack(app, 'BootstrapStack');
