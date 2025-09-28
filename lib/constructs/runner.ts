
import * as events from 'aws-cdk-lib/aws-events';
import { IConstruct } from 'constructs';

/**
 * Represents a runner that can be triggered by an EventBridge rule.
 */
export interface IRunner extends IConstruct {
  /**
   * The target for the EventBridge rule to start the runner.
   */
  readonly startTarget: events.IRuleTarget;

  /**
   * A unique identifier for the runner, such as a CodeBuild project name.
   * Used for creating event filters.
   */
  readonly runnerName: string;

  /**
   * Environment variables that will be available to the runner.
   */
  readonly env: { [key: string]: string };
}
