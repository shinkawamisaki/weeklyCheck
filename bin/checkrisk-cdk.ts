#!/usr/bin/env node
import 'source-map-support/register';
import 'dotenv/config';
import * as cdk from 'aws-cdk-lib';
import { CheckRiskStack } from '../lib/checkrisk-cdk-stack';

// ##################################################################
// ##            CONFIGURATION - VIA ENVIRONMENT VARIABLES         ##
// ##################################################################

// Read all configuration from environment variables. No hardcoding.

// (Required) The full, raw URL to your checkRisk.sh script on GitHub.
const sourceUrl = process.env.SCRIPT_SOURCE_URL;

// (Recommended) SHA-256 of that script. CodeBuild verifies the download against it before running.
// Compute with: curl -fsSL "$SCRIPT_SOURCE_URL" | shasum -a 256
const scriptSha256 = process.env.SCRIPT_SHA256?.trim().toLowerCase() || undefined;

// (Optional) The name of the AWS Secrets Manager secret for Slack.
// Defaults to 'slack/bot' if not set.
const slackSecretName = process.env.SLACK_SECRET_NAME || 'slack/bot';

// (Optional) The name of the secret for your OpenAI API key.
// Defaults to 'openai/prod/key' if not set.
const openAiSecretName = process.env.OPENAI_SECRET_NAME || 'openai/prod/key';

// (Optional) The name of the secret for your GitHub Personal Access Token (PAT).
// Only needed when the script lives in a private repository. Unset = no PAT lookup, no IAM grant.
const githubPatSecretName = process.env.GITHUB_PAT_SECRET_NAME || undefined;

// (Optional) Set to '1' or 'true' to enable OpenAI summary.
// Defaults to false if not set.
const polishWithOpenAi = /^(1|true)$/i.test(process.env.POLISH_WITH_OPENAI || '');

// ##################################################################

// Validate that the mandatory SCRIPT_SOURCE_URL is provided.
if (!sourceUrl) {
  throw new Error('Mandatory environment variable SCRIPT_SOURCE_URL is not set. Please set it before deploying.');
}
if (scriptSha256 && !/^[0-9a-f]{64}$/.test(scriptSha256)) {
  throw new Error('SCRIPT_SHA256 must be a 64-character hex SHA-256 digest.');
}

const app = new cdk.App();

new CheckRiskStack(app, 'CheckRiskStack', {
  // The stack name will be 'CheckRiskStack'.
  // You can customize it here if needed, e.g., stackName: 'MyCustomCheckRiskStack'
  
  // Pass the configured properties to the stack.
  sourceUrl: sourceUrl,
  scriptSha256: scriptSha256,
  slackSecretName: slackSecretName,
  openAiSecretName: openAiSecretName,
  githubPatSecretName: githubPatSecretName,
  polishWithOpenAi: polishWithOpenAi,

  /* For deploying to a different AWS account and region: */
  /*
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
  */
});