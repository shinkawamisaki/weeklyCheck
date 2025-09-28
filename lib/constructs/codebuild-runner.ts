
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3_assets from 'aws-cdk-lib/aws-s3-assets';
import * as cdk from 'aws-cdk-lib';
import * as path from 'path';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import { IRunner } from './runner';

export interface CodeBuildRunnerProps {
  projectName: string;
  sourceUrl: string;
  artifactBucket: s3.Bucket;
  slackSecretName: string;
  openAiSecretName?: string;
  githubPatSecretName?: string;
  polishWithOpenAi?: boolean;
}

export class CodeBuildRunner extends Construct implements IRunner {
  public readonly startTarget: events.IRuleTarget;
  public readonly runnerName: string;
  public readonly env: { [key: string]: string };

  private readonly project: codebuild.Project;

  constructor(scope: Construct, id: string, props: CodeBuildRunnerProps) {
    super(scope, id);

    const codeBuildRole = new iam.Role(this, 'CodeBuildRole', {
      assumedBy: new iam.ServicePrincipal('codebuild.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('SecurityAudit'),
      ],
    });

    props.artifactBucket.grantReadWrite(codeBuildRole);

    const secretArns = [
      `arn:aws:secretsmanager:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:secret:${props.slackSecretName}-*`,
    ];
    if (props.openAiSecretName) {
      secretArns.push(`arn:aws:secretsmanager:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:secret:${props.openAiSecretName}-*`);
    }
    if (props.githubPatSecretName) {
      secretArns.push(`arn:aws:secretsmanager:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:secret:${props.githubPatSecretName}-*`);
    }

    codeBuildRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['secretsmanager:GetSecretValue'],
      resources: secretArns,
    }));

    const buildSpecAsset = new s3_assets.Asset(this, 'BuildSpecAsset', {
      path: path.join(__dirname, '../../assets/buildspec'),
    });

    const environmentVariables = {
      REPORTS_BUCKET: { value: props.artifactBucket.bucketName },
      SRC_URL: { value: props.sourceUrl },
      GITHUB_PAT_SECRET_NAME: { value: props.githubPatSecretName || '' },
      OPENAI_SECRET_NAME: { value: props.openAiSecretName || '' },
      ...(props.polishWithOpenAi && { POLISH_WITH_OPENAI: { value: '1' } }),
    };

    this.project = new codebuild.Project(this, 'CheckRiskProject', {
      projectName: props.projectName,
      role: codeBuildRole,
      source: codebuild.Source.s3({
        bucket: buildSpecAsset.bucket,
        path: buildSpecAsset.s3ObjectKey,
      }),
      artifacts: codebuild.Artifacts.s3({
        bucket: props.artifactBucket,
        path: '',
        includeBuildId: false,
        packageZip: false,

      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
      },
      environmentVariables: environmentVariables,
    });

    // Populate IRunner interface properties
    this.startTarget = new targets.CodeBuildProject(this.project);
    this.runnerName = this.project.projectName;
    this.env = Object.entries(environmentVariables).reduce((acc, [key, val]) => {
        if (val.value) {
            acc[key] = val.value;
        }
        return acc;
    }, {} as { [key: string]: string });
  }
}
