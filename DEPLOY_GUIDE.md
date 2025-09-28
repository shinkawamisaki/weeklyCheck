# AWS Risk Weekly (CDK) – デプロイガイド

このリポジトリは、指定したシェルスクリプト（例: `checkRisk.sh`）を**週次**で実行し、結果を S3 に保存し、Slack に要約を通知するワークフローを **AWS CDK** で構築します。実行フローは **EventBridge → CodeBuild → S3 → Lambda(→ Slack)** のシンプルな構成です。

- **デフォルトのスケジュール**: 毎週 **月曜 00:00 UTC**（JST 09:00）。必要に応じて変更してください。

## 対応環境（OS非依存の想定）
- macOS / Linux（bash/zsh）
- Windows は WSL2 推奨（ネイティブ PowerShell でも可）
- いずれの環境でも **AWS CLI** 認証設定と **Docker** が動作していること（Lambda 依存関係のパッケージングに使用）

## 前提条件
- **AWS アカウント & AWS CLI**（初回は IAM / S3 / Lambda 作成権限が必要）  
- **Node.js 16+ / npm**  
- **AWS CDK** (`npm install -g aws-cdk`)  
- **Docker Desktop / Docker デーモン** を起動しておく  

## セキュリティ情報（AWS Secrets Manager）
本プロジェクトは機密値を **AWS Secrets Manager** に保存して参照します。事前に必要なシークレットを作成してください。

### 必須: Slack Bot
- Bot Token（`xoxb-...`）に `chat:write`, `files:write` を付与し、通知チャンネルに招待して **チャンネルID** を取得  
- 例（リージョンは適宜置換）:
```sh
aws secretsmanager create-secret   --name "slack/bot"   --secret-string '{"bot_token":"<BOT_TOKEN>","channel_id":"<CHANNEL_ID>"}'   --region <REGION>
```

### 任意: OpenAI（要約強化）
```sh
aws secretsmanager create-secret   --name "openai/prod/key"   --secret-string '{"OPENAI_API_KEY":"<OPENAI_API_KEY>"}'   --region <REGION>
```

### 任意: GitHub PAT（私有リポからスクリプト取得する場合）
```sh
aws secretsmanager create-secret   --name "github/pat"   --secret-string '{"token":"<GITHUB_PAT>"}'   --region <REGION>
```

## 設定（環境変数）
ソースコードの改変は不要です。**環境変数**（`.env` 推奨）で設定します。`.env` はリポジトリ直下または `checkrisk-cdk` ディレクトリに配置できます。
添付のENVは「SCRIPT_SOURCE_URL="https://raw.githubusercontent.com/shinkawamisaki/checkRisk/e3965152e0ee1ea80f10582e41e766dda30f3edd/checkRisk.sh"」設定済み
GPT要約はオフ（0）です。

`.env` の例:
```
# (必須) 実行するシェルスクリプトの Raw URL
# 例: https://raw.githubusercontent.com/<OWNER>/<REPO>/<REF>/checkRisk.sh
SCRIPT_SOURCE_URL="<REPLACE_WITH_YOUR_RAW_URL>"

# (任意) GPT 要約を有効化（"1" または "true"）
# POLISH_WITH_OPENAI="1"

# (任意) デフォルト名を変更した場合は上書き
# SLACK_SECRET_NAME="slack/bot"
# OPENAI_SECRET_NAME="openai/prod/key"
# GITHUB_PAT_SECRET_NAME="github/pat"
```

## デプロイ（3ステップ）
```sh
# 1) 依存のインストール
npm install

# 2) 初回のみブートストラップ（アカウント/リージョンごと）
cdk bootstrap

# 3) デプロイ
cdk deploy
```
> `.env` は自動で読み込まれる設計です。

## 動作確認（任意）
すぐに試す場合は CodeBuild を手動実行:
```sh
aws codebuild start-build --project-name aws-risk-weekly
```
（詳細ログは CloudWatch Logs を確認）

## クリーンアップ
作成した AWS リソースを削除:
```sh
cdk destroy
```

## トラブルシューティング（短縮版）
- **Docker が起動していない** → Lambda 依存解決で失敗します（Docker を起動）  
- **ブートストラップ未実施** → `cdk bootstrap` を先に実行  
- **リージョン/認証不整合** → `aws ... --region <REGION>` と認証プロファイルを統一

## ライセンス
リポジトリ内の **LICENSE** をご確認ください。
