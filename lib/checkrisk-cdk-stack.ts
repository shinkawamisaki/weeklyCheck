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
  /** sourceUrl のスクリプトの SHA-256。指定すると CodeBuild がダウンロード後に照合する */
  scriptSha256?: string;
  slackSecretName: string;
  openAiSecretName?: string;
  githubPatSecretName?: string;
  polishWithOpenAi?: boolean;
  /** レポートの保持日数（既定 365） */
  reportRetentionDays?: number;
  /** true なら cdk destroy でレポートバケットを残す */
  retainBucket?: boolean;
}

export class CheckRiskStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CheckRiskStackProps) {
    super(scope, id, props);

    const projectName = props.projectName || 'aws-risk-weekly';

    // 1. Create the Storage layer (S3 Bucket)
    const storage = new Storage(this, 'Storage', {
      projectName: projectName,
      retentionDays: props.reportRetentionDays,
      retain: props.retainBucket,
    });

    // 2. Create the Runner layer (CodeBuildRunner)
    const runner = new CodeBuildRunner(this, 'Collector', {
      projectName: projectName,
      artifactBucket: storage.bucket,
      sourceUrl: props.sourceUrl,
      scriptSha256: props.scriptSha256,
      polishWithOpenAi: props.polishWithOpenAi,
      openAiSecretName: props.openAiSecretName,
      githubPatSecretName: props.githubPatSecretName,
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