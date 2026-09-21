### 🔴 今すぐ対応（Top5）
1. root の MFA が未設定
2. root にアクセスキーが存在
3. S3 バケット public-bucket が公開
4. CloudTrail が停止中
5. GuardDuty が未有効化

# AWSセキュリティ監査レポート（要約）
- リージョン: ap-northeast-1
- アカウント: 11**********

## サマリー

- Critical: 1
- High:     17
- Medium:   9
- Low:      8

### 📝 短評
全体として基本設定の抜けが多い。

## IAM

| 対象 | 設定 | リスク | 優先度 |
|------|------|------|------|
| root | MFA=未設定 | ⚠️ root MFA未設定 | Critical |
