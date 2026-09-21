
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cdk from 'aws-cdk-lib';

export interface StorageProps {
    projectName: string;
    /** レポートの保持日数。これを過ぎたレポートはライフサイクルで削除する（既定 365 日） */
    retentionDays?: number;
    /** true なら cdk destroy でバケットと中身を残す。既定はデモ向けに削除する */
    retain?: boolean;
}

export class Storage extends Construct {
    public readonly bucket: s3.Bucket;

    constructor(scope: Construct, id: string, props: StorageProps) {
        super(scope, id);

        const retentionDays = props.retentionDays ?? 365;
        const retain = props.retain ?? false;

        // レポートにはアカウントの設定不備がそのまま書かれている。公開ブロックと TLS 必須を明示する
        this.bucket = new s3.Bucket(this, 'ArtifactBucket', {
            bucketName: `${props.projectName.toLowerCase()}-${cdk.Aws.ACCOUNT_ID}-${cdk.Aws.REGION}`,
            versioned: true,
            encryption: s3.BucketEncryption.S3_MANAGED,
            enforceSSL: true,
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            lifecycleRules: [{
                id: 'expire-old-reports',
                expiration: cdk.Duration.days(retentionDays),
                noncurrentVersionExpiration: cdk.Duration.days(30),
                abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
            }],
            removalPolicy: retain ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
            autoDeleteObjects: !retain,
        });
    }
}
