
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
  /** 実行するスクリプトの Raw URL（コミット SHA かタグで固定すること） */
  sourceUrl: string;
  artifactBucket: s3.Bucket;
  /** OpenAI 整形を有効にする。有効なときだけ openAiSecretName の読取権限を付与する */
  polishWithOpenAi?: boolean;
  openAiSecretName?: string;
  /** 私有リポジトリから取得する場合の GitHub PAT シークレット名。未指定なら PAT は取得しない */
  githubPatSecretName?: string;
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

    // Secrets Manager の読取は「実際に使うシークレット」だけに絞る。
    // Slack のシークレットは Notifier(Lambda) だけが読むので CodeBuild には付与しない。
    const secretArns: string[] = [];
    const usesOpenAi = !!(props.polishWithOpenAi && props.openAiSecretName);
    if (usesOpenAi) {
      secretArns.push(`arn:aws:secretsmanager:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:secret:${props.openAiSecretName}-*`);
    }
    if (props.githubPatSecretName) {
      secretArns.push(`arn:aws:secretsmanager:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:secret:${props.githubPatSecretName}-*`);
    }
    if (secretArns.length > 0) {
      codeBuildRole.addToPolicy(new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['secretsmanager:GetSecretValue'],
        resources: secretArns,
      }));
    }

    const buildSpecAsset = new s3_assets.Asset(this, 'BuildSpecAsset', {
      path: path.join(__dirname, '../../assets/buildspec'),
    });

    const environmentVariables: { [name: string]: codebuild.BuildEnvironmentVariable } = {
      REPORTS_BUCKET: { value: props.artifactBucket.bucketName },
      SRC_URL: { value: props.sourceUrl },
      ...(props.githubPatSecretName && { GITHUB_PAT_SECRET_NAME: { value: props.githubPatSecretName } }),
      ...(usesOpenAi && {
        POLISH_WITH_OPENAI: { value: '1' },
        OPENAI_SECRET_NAME: { value: props.openAiSecretName! },
      }),
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
        // Ubuntu 24.04 (standard:8.0)。aws-cdk-lib 2.270 時点で定数が無いので ID 指定
        buildImage: codebuild.LinuxBuildImage.fromCodeBuildImageId('aws/codebuild/standard:8.0'),
      },
      environmentVariables: environmentVariables,
    });

    // Populate IRunner interface properties
    this.startTarget = new targets.CodeBuildProject(this.project);
    this.runnerName = this.project.projectName;
    this.env = Object.entries(environmentVariables).reduce((acc, [key, val]) => {
      if (typeof val.value === 'string' && val.value) {
        acc[key] = val.value;
      }
      return acc;
    }, {} as { [key: string]: string });
  }
}
