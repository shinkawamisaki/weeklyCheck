import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { CheckRiskStack, CheckRiskStackProps } from '../lib/checkrisk-cdk-stack';

const SRC = 'https://raw.githubusercontent.com/example/checkRisk/0123456789abcdef/checkRisk.sh';

function synth(overrides: Partial<CheckRiskStackProps> = {}): Template {
  // Lambda のバンドル（Docker）を走らせずにテンプレートだけ生成する
  const app = new cdk.App({ context: { 'aws:cdk:bundling-stacks': [] } });
  const stack = new CheckRiskStack(app, 'TestStack', {
    sourceUrl: SRC,
    slackSecretName: 'slack/bot',
    openAiSecretName: 'openai/prod/key',
    ...overrides,
  });
  return Template.fromStack(stack);
}

/** ロール名の接頭辞で IAM::Policy を探し、Statement をまとめて返す */
function statementsOfRole(template: Template, roleIdPrefix: string): any[] {
  const policies = template.findResources('AWS::IAM::Policy');
  return Object.values(policies)
    .filter((p: any) => (p.Properties.Roles ?? []).some((r: any) => JSON.stringify(r).includes(roleIdPrefix)))
    .flatMap((p: any) => p.Properties.PolicyDocument.Statement);
}

describe('スケジュールと連携', () => {
  test('毎週月曜 00:00 UTC (JST 09:00) に CodeBuild を起動する', () => {
    const t = synth();
    t.hasResourceProperties('AWS::Events::Rule', {
      ScheduleExpression: 'cron(0 0 ? * MON *)',
      State: 'ENABLED',
    });
  });

  test('CodeBuild が SUCCEEDED になったら outcome=success で Slack 通知 Lambda を起動する', () => {
    const t = synth();
    t.hasResourceProperties('AWS::Events::Rule', {
      EventPattern: {
        source: ['aws.codebuild'],
        'detail-type': ['CodeBuild Build State Change'],
        detail: Match.objectLike({ 'build-status': ['SUCCEEDED'] }),
      },
      Targets: [Match.objectLike({
        InputTransformer: Match.objectLike({
          InputTemplate: { 'Fn::Join': ['', Match.arrayWith([Match.stringLikeRegexp('"outcome":"success"')])] },
        }),
        RetryPolicy: Match.objectLike({ MaximumRetryAttempts: 1 }),
      })],
    });
  });

  test('CodeBuild が失敗系の状態になったら outcome=failure で同じ Lambda を起動する', () => {
    const t = synth();
    t.hasResourceProperties('AWS::Events::Rule', {
      EventPattern: {
        source: ['aws.codebuild'],
        'detail-type': ['CodeBuild Build State Change'],
        detail: Match.objectLike({ 'build-status': ['FAILED', 'FAULT', 'STOPPED', 'TIMED_OUT'] }),
      },
      Targets: [Match.objectLike({
        InputTransformer: Match.objectLike({
          InputPathsMap: Match.objectLike({ detail: '$.detail' }),
          // detail は引用符なしで埋め込む（JSON オブジェクトごと Lambda に渡す）
          InputTemplate: { 'Fn::Join': ['', Match.arrayWith([
            Match.stringLikeRegexp('"outcome":"failure"'),
            Match.stringLikeRegexp('"detail":<detail>\\}$'),
          ])] },
        }),
      })],
    });
  });
});

describe('CodeBuild の権限と環境変数', () => {
  test('SecurityAudit を持ち、Slack のシークレットは読めない', () => {
    const t = synth();
    t.hasResourceProperties('AWS::IAM::Role', {
      AssumeRolePolicyDocument: Match.objectLike({
        Statement: [Match.objectLike({ Principal: { Service: 'codebuild.amazonaws.com' } })],
      }),
      ManagedPolicyArns: [Match.objectLike({ 'Fn::Join': Match.arrayWith([Match.arrayWith([':iam::aws:policy/SecurityAudit'])]) })],
    });
    const stmts = JSON.stringify(statementsOfRole(t, 'CollectorCodeBuildRole'));
    expect(stmts).not.toContain('slack/bot');
  });

  test('既定では OpenAI/PAT のシークレット権限も環境変数も付かない', () => {
    const t = synth();
    const stmts = JSON.stringify(statementsOfRole(t, 'CollectorCodeBuildRole'));
    expect(stmts).not.toContain('secretsmanager:GetSecretValue');
    const project = Object.values(t.findResources('AWS::CodeBuild::Project'))[0] as any;
    const names = project.Properties.Environment.EnvironmentVariables.map((v: any) => v.Name);
    expect(names).toEqual(expect.arrayContaining(['REPORTS_BUCKET', 'SRC_URL']));
    expect(names).not.toContain('OPENAI_SECRET_NAME');
    expect(names).not.toContain('GITHUB_PAT_SECRET_NAME');
    expect(names).not.toContain('POLISH_WITH_OPENAI');
  });

  test('OpenAI 整形を有効にしたときだけ OpenAI シークレットの読取と環境変数が付く', () => {
    const t = synth({ polishWithOpenAi: true });
    const stmts = JSON.stringify(statementsOfRole(t, 'CollectorCodeBuildRole'));
    expect(stmts).toContain('openai/prod/key');
    expect(stmts).not.toContain('slack/bot');
    const project = Object.values(t.findResources('AWS::CodeBuild::Project'))[0] as any;
    const env = Object.fromEntries(project.Properties.Environment.EnvironmentVariables.map((v: any) => [v.Name, v.Value]));
    expect(env.POLISH_WITH_OPENAI).toBe('1');
    expect(env.OPENAI_SECRET_NAME).toBe('openai/prod/key');
  });

  test('GitHub PAT を指定したときだけ PAT シークレットの読取が付く', () => {
    const t = synth({ githubPatSecretName: 'github/pat' });
    const stmts = JSON.stringify(statementsOfRole(t, 'CollectorCodeBuildRole'));
    expect(stmts).toContain('github/pat');
    expect(stmts).not.toContain('openai/prod/key');
  });
});

describe('Slack 通知 Lambda', () => {
  test('レポートバケットと Slack シークレット名を環境変数で受け取る', () => {
    const t = synth();
    t.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'aws-risk-weekly-slack',
      Environment: { Variables: Match.objectLike({ SLACK_SECRET_NAME: 'slack/bot', S3_BUCKET: Match.anyValue() }) },
    });
  });

  test('読めるシークレットは Slack のものだけ', () => {
    const t = synth({ polishWithOpenAi: true, githubPatSecretName: 'github/pat' });
    const stmts = JSON.stringify(statementsOfRole(t, 'NotifierSlackLambdaRole'));
    expect(stmts).toContain('slack/bot');
    expect(stmts).not.toContain('openai/prod/key');
    expect(stmts).not.toContain('github/pat');
  });
});

describe('レポート保管バケット', () => {
  test('バージョニングと SSE が有効', () => {
    const t = synth();
    t.hasResourceProperties('AWS::S3::Bucket', {
      VersioningConfiguration: { Status: 'Enabled' },
      BucketEncryption: Match.objectLike({}),
    });
  });
});
