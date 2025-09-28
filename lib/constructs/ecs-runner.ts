
import { Construct } from 'constructs';
import * as events from 'aws-cdk-lib/aws-events';
import { IRunner } from './runner';

export interface EcsRunnerProps {
  // Define properties for the ECS runner here in the future
}

/**
 * A skeleton for a future ECS/Fargate runner implementation.
 * This is not yet implemented.
 */
export class EcsRunner extends Construct implements IRunner {
  public readonly startTarget: events.IRuleTarget;
  public readonly env: { [key: string]: string };
  public readonly runnerName: string;

  constructor(scope: Construct, id: string, props: EcsRunnerProps) {
    super(scope, id);

    // This is a placeholder and does not represent a real implementation.
    this.env = {};
    this.runnerName = 'ecs-runner-placeholder'; // Satisfy the interface

    // The actual implementation would create an EcsTask target.
    // For now, we use a dummy target to satisfy the interface.
    this.startTarget = {
      bind: () => ({
        id: '',
        arn: '',
      }),
    };

    // Throw an error if someone tries to use this construct
    throw new Error('EcsRunner is a skeleton and not yet implemented. Do not use.');
  }
}
