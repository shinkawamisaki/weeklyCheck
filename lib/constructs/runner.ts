
import * as events from 'aws-cdk-lib/aws-events';
import { IConstruct } from 'constructs';

/**
 * スクリプト実行環境（CodeBuild / ECS など）の共通インターフェース。
 *
 * Scheduler はこのインターフェースだけを見て「いつ起動するか」「終わったらどう通知するか」を組み立てる。
 * 実行環境を差し替えるときは IRunner の実装を 1 つ足せばよく、Scheduler と Notifier は変更しない。
 */
export interface IRunner extends IConstruct {
  /** EventBridge のスケジュールルールから起動するためのターゲット */
  readonly startTarget: events.IRuleTarget;

  /** 実行環境の一意な名前。通知本文や識別に使う */
  readonly runnerName: string;

  /** この Runner の「正常終了」を表す EventBridge のイベントパターン */
  readonly successEventPattern: events.EventPattern;

  /** この Runner の「異常終了（失敗・停止・タイムアウトなど）」を表すイベントパターン */
  readonly failureEventPattern: events.EventPattern;
}
