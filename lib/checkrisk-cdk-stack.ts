import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Storage } from './constructs/store';
import { CodeBuildRunner } from './constructs/codebuild-runner';
import { Notifier } from './constructs/notifier';
import { Scheduler } from './constructs/schedule';

// Stack properties interface for configurability
export interface CheckRiskStackProps extends cdk.StackProps {
  projectName?: string;
  sourceUrl: string;
  slackSecretName: string;
  openAiSecretName?: string;
  githubPatSecretName?: string;
  polishWithOpenAi?: boolean;
}

export class CheckRiskStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CheckRiskStackProps) {
    super(scope, id, props);

    const projectName = props.projectName || 'aws-risk-weekly';

    // 1. Create the Storage layer (S3 Bucket)
    const storage = new Storage(this, 'Storage', {
      projectName: projectName,
    });

    // 2. Create the Runner layer (CodeBuildRunner)
    const runner = new CodeBuildRunner(this, 'Collector', {
      projectName: projectName,
      artifactBucket: storage.bucket,
      sourceUrl: props.sourceUrl,
      slackSecretName: props.slackSecretName,
      openAiSecretName: props.openAiSecretName,
      githubPatSecretName: props.githubPatSecretName,
      polishWithOpenAi: props.polishWithOpenAi,
    });

    // 3. Create the Notifier layer (Lambda)
    const notifier = new Notifier(this, 'Notifier', {
      projectName: projectName,
      artifactBucket: storage.bucket,
      slackSecretName: props.slackSecretName,
      polishWithOpenAi: props.polishWithOpenAi,
    });

    // 4. Create the Scheduler layer (EventBridge)
    new Scheduler(this, 'Scheduler', {
      projectName: projectName,
      runner: runner,
      notifierFunction: notifier.func,
    });
  }
}