
import { Construct } from 'constructs';
import * as cdk from 'aws-cdk-lib';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { IRunner } from './runner';

export interface SchedulerProps {
    projectName: string;
    runner: IRunner;
    notifierFunction: lambda.IFunction;
    /** 実行スケジュール。既定は毎週月曜 00:00 UTC（JST 09:00） */
    schedule?: events.Schedule;
}

export class Scheduler extends Construct {
    constructor(scope: Construct, id: string, props: SchedulerProps) {
        super(scope, id);

        // Rule 1: 週次スケジュールで Runner を起動
        const weeklyRule = new events.Rule(this, 'WeeklyCronRule', {
            ruleName: `${props.projectName}-weekly-cron`,
            schedule: props.schedule ?? events.Schedule.expression('cron(0 0 ? * MON *)'),
        });
        weeklyRule.addTarget(props.runner.startTarget);

        // Notifier には「成功か失敗か」を EventBridge 側で付けて渡す。
        // Lambda は Runner の種類（CodeBuild / ECS…）を知らなくてよい。
        const notify = (outcome: 'success' | 'failure') => new targets.LambdaFunction(props.notifierFunction, {
            event: events.RuleTargetInput.fromObject({
                outcome,
                runner: props.runner.runnerName,
                detail: events.EventField.fromPath('$.detail'),
            }),
            // 既定 (185 回/24h) だと Slack 側の一時障害で同じ通知が何度も飛ぶ。1 回だけ再試行する
            retryAttempts: 1,
            maxEventAge: cdk.Duration.hours(2),
        });

        // Rule 2: Runner 成功 → レポート通知
        // イベントパターンは Runner 自身が持つ。Scheduler は CodeBuild か ECS かを知らない
        new events.Rule(this, 'OnSuccessRule', {
            ruleName: `${props.projectName}-on-success`,
            eventPattern: props.runner.successEventPattern,
            targets: [notify('success')],
        });

        // Rule 3: Runner 失敗 → 「実行できませんでした」を通知（無通知＝正常、にしない）
        new events.Rule(this, 'OnFailureRule', {
            ruleName: `${props.projectName}-on-failure`,
            eventPattern: props.runner.failureEventPattern,
            targets: [notify('failure')],
        });
    }
}
