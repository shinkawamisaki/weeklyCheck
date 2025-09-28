
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cdk from 'aws-cdk-lib';

export interface StorageProps {
    projectName: string;
}

export class Storage extends Construct {
    public readonly bucket: s3.Bucket;

    constructor(scope: Construct, id: string, props: StorageProps) {
        super(scope, id);

        this.bucket = new s3.Bucket(this, 'ArtifactBucket', {
            bucketName: `${props.projectName.toLowerCase()}-${cdk.Aws.ACCOUNT_ID}-${cdk.Aws.REGION}`,
            versioned: true,
            encryption: s3.BucketEncryption.S3_MANAGED,
            removalPolicy: cdk.RemovalPolicy.DESTROY, // For demo purposes
            autoDeleteObjects: true, // For demo purposes
        });
    }
}
