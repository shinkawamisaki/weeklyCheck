import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { PythonFunction } from '@aws-cdk/aws-lambda-python-alpha';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cdk from 'aws-cdk-lib';
import * as path from 'path';
import * as logs from 'aws-cdk-lib/aws-logs';

export interface NotifierProps {
    projectName: string;
    artifactBucket: s3.Bucket;
    slackSecretName: string;
    polishWithOpenAi?: boolean;
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

        this.func = new PythonFunction(this, 'SlackNotifierFunction', {
            functionName: `${props.projectName}-slack`,
            entry: path.join(__dirname, '../../lambda'),
            runtime: lambda.Runtime.PYTHON_3_11,
            handler: 'handler',
            index: 'lambda_function.py',
            role: lambdaRole,
            environment: {
                S3_BUCKET: props.artifactBucket.bucketName,
                S3_PREFIX: '',
                SLACK_SECRET_NAME: props.slackSecretName,
                ...(props.polishWithOpenAi && { POLISH_WITH_OPENAI: 'true' }),
            },
            timeout: cdk.Duration.minutes(1),
            logGroup: logGroup,
        });
    }
}