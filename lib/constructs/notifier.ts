import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cdk from 'aws-cdk-lib';
import * as path from 'path';
import * as logs from 'aws-cdk-lib/aws-logs';

export interface NotifierProps {
    projectName: string;
    artifactBucket: s3.Bucket;
    slackSecretName: string;
    polishWithOpenAi?: boolean;
    /** 成功イベント時に、これより古いレポートしか無ければ「見つからない」扱いにする（既定 24 時間） */
    maxReportAgeHours?: number;
}

export class Notifier extends Construct {
    public readonly func: lambda.IFunction;

    constructor(scope: Construct, id: string, props: NotifierProps) {
        super(scope, id);

        const lambdaRole = new iam.Role(this, 'SlackLambdaRole', {
            assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [
                iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
            ],
        });

        props.artifactBucket.grantRead(lambdaRole);

        const secretArn = `arn:aws:secretsmanager:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:secret:${props.slackSecretName}-*`;
        lambdaRole.addToPolicy(new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ['secretsmanager:GetSecretValue'],
            resources: [secretArn],
        }));

        const logGroup = new logs.LogGroup(this, 'SlackNotifierLogGroup', {
            logGroupName: `/aws/lambda/${props.projectName}-slack`,
            retention: logs.RetentionDays.ONE_MONTH,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        });

        // 外部ライブラリを使わない（標準ライブラリ + 同梱 boto3）ので、Docker でのバンドル無しに zip できる
        this.func = new lambda.Function(this, 'SlackNotifierFunction', {
            functionName: `${props.projectName}-slack`,
            code: lambda.Code.fromAsset(path.join(__dirname, '../../lambda'), {
                exclude: ['__pycache__', '*.pyc', 'requirements.txt'],
            }),
            runtime: lambda.Runtime.PYTHON_3_13,  // AL2023 系。3.11 は AL2 系で 2027-06-30 非推奨
            handler: 'lambda_function.handler',
            role: lambdaRole,
            environment: {
                S3_BUCKET: props.artifactBucket.bucketName,
                S3_PREFIX: '',
                SLACK_SECRET_NAME: props.slackSecretName,
                MAX_REPORT_AGE_HOURS: String(props.maxReportAgeHours ?? 24),
                ...(props.polishWithOpenAi && { POLISH_WITH_OPENAI: 'true' }),
            },
            timeout: cdk.Duration.minutes(1),
            logGroup: logGroup,
        });
    }
}
