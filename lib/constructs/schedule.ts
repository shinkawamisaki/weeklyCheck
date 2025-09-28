
import { Construct } from 'constructs';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { IRunner } from './runner';

export interface SchedulerProps {
    projectName: string;
    runner: IRunner;
    notifierFunction: lambda.IFunction;
}

export class Scheduler extends Construct {
    constructor(scope: Construct, id: string, props: SchedulerProps) {
        super(scope, id);

        // Rule 1: Weekly cron job to trigger the runner
        const weeklyRule = new events.Rule(this, 'WeeklyCronRule', {
            ruleName: `${props.projectName}-weekly-cron`,
            schedule: events.Schedule.expression('cron(0 0 ? * MON *)'), // UTC 00:00 on Monday
        });

        weeklyRule.addTarget(props.runner.startTarget);

        // Rule 2: Trigger Lambda on runner's success
        // Note: The event source is currently specific to CodeBuild.
        // This would need to be generalized if a different runner type (e.g., ECS) is used.
        const onSuccessRule = new events.Rule(this, 'OnSuccessRule', {
            ruleName: `${props.projectName}-on-success`,
            eventPattern: {
                source: ['aws.codebuild'],
                detailType: ['CodeBuild Build State Change'],
                detail: {
                    'build-status': ['SUCCEEDED'],
                    'project-name': [props.runner.runnerName],
                },
            },
        });

        onSuccessRule.addTarget(new targets.LambdaFunction(props.notifierFunction));
    }
}
