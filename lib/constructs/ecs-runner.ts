
import { Construct } from 'constructs';
import * as events from 'aws-cdk-lib/aws-events';
import { IRunner } from './runner';

export interface EcsRunnerProps {
  // 将来 ECS/Fargate で動かすときのプロパティ（クラスタ、タスク定義、サブネットなど）をここに定義する
}

/**
 * ECS/Fargate で実行する Runner の骨組み。まだ実装していない。
 *
 * 実装するときに必要なもの:
 * - startTarget: targets.EcsTask（タスク定義とクラスタを指定）
 * - successEventPattern / failureEventPattern: 「ECS Task State Change」イベントで
 *   lastStatus=STOPPED かつコンテナの exitCode が 0 か否かで分ける（下記は形の例で、未検証）
 * Scheduler と Notifier はこのインターフェース越しにしか Runner を見ないので変更不要。
 */
export class EcsRunner extends Construct implements IRunner {
  public readonly startTarget: events.IRuleTarget;
  public readonly runnerName: string;
  public readonly successEventPattern: events.EventPattern;
  public readonly failureEventPattern: events.EventPattern;

  constructor(scope: Construct, id: string, _props: EcsRunnerProps) {
    super(scope, id);

    this.runnerName = 'ecs-runner-placeholder';
    this.successEventPattern = {
      source: ['aws.ecs'],
      detailType: ['ECS Task State Change'],
      detail: { lastStatus: ['STOPPED'], containers: { exitCode: [0] } },
    };
    this.failureEventPattern = {
      source: ['aws.ecs'],
      detailType: ['ECS Task State Change'],
      detail: { lastStatus: ['STOPPED'], containers: { exitCode: [{ 'anything-but': [0] }] } },
    };
    this.startTarget = { bind: () => ({ id: '', arn: '' }) };

    throw new Error('EcsRunner is a skeleton and not yet implemented. Do not use.');
  }
}
