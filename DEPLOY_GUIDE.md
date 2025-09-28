# デプロイガイド: AWS Risk Weekly CDK

このガイドでは、AWS Risk Weekly CDKプロジェクトをあなた自身のAWSアカウントにデプロイする方法を説明します。

## 概要

このプロジェクトは、指定されたリスクチェック用のシェルスクリプト (`checkRisk.sh`) を週次スケジュールで自動実行します。AWS CodeBuildでスクリプトを実行し、AWS LambdaでSlackにサマリーレポートを送信する構成です。

- **週次トリガー**: Amazon EventBridgeルールにより、毎週月曜日の00:00 UTC (日本時間 9:00) に実行されます。
- **実行**: AWS CodeBuildプロジェクトが、指定された `checkRisk.sh` スクリプトをダウンロードして実行します。
- **保管**: 出力されたレポート（Markdownファイル）はAmazon S3バケットに保存されます。
- **通知**: 実行が成功すると、AWS Lambda関数がレポートの要約をSlackチャンネルに送信し、完全なレポートを添付します。

## 1. 前提条件

作業を始める前に、以下がインストールされ、設定済みであることを確認してください。

1.  **AWSアカウントとCLI**: AWSアカウントと、認証情報が設定された [AWS CLI](https://aws.amazon.com/cli/)。初回デプロイには、IAMロール、S3バケット、Lambda関数などを作成する権限が必要です。
2.  **Node.js と npm**: [Node.js](https://nodejs.org/) (バージョン16以降) と npm。
3.  **AWS CDK Toolkit**: AWS CDKのコマンドラインツール。以下のコマンドでグローバルインストールしてください。
    ```sh
    npm install -g aws-cdk
    ```
4.  **Docker**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) がインストールされ、**実行中**である必要があります。CDKは、Python Lambda関数の依存関係をパッケージ化するためにDockerを使用します。

## 2. セットアップ: シークレットの作成

このアプリケーションは、APIキーやトークンといった機密情報を **AWS Secrets Manager** に安全に保存して利用します。デプロイの前に、これらのシークレットを作成する必要があります。

### Slack (必須)

1.  Slackアプリを作成し、**Bot User OAuth Token** (`xoxb-...`) を取得します。アプリには `chat:write` と `files:write` のスコープを付与してください。
2.  Botを通知先のチャンネルに招待し、その**チャンネルID** (`C...`) を取得します。
3.  以下のAWS CLIコマンドを実行します。プレースホルダーの値は実際のトークン、チャンネルIDに置き換えてください。シークレット名は、デフォルトの `slack/bot` を推奨します。

```sh
aws secretsmanager create-secret --name "slack/bot" --secret-string '{"bot_token":"Botのトークン","channel_id":"チャンネルID"}' --region ap-northeast-1  # <-- あなたのAWSリージョンに置き換えてください
```

### OpenAI APIキー (任意)

GPTによる要約機能を利用する場合は、以下のシークレットを作成します。デフォルトのシークレット名は `openai/prod/key` です。

```sh
aws secretsmanager create-secret --name "openai/prod/key" --secret-string '{"OPENAI_API_KEY":"GPTのAPIキー"}' --region ap-northeast-1 # <-- あなたのAWSリージョンに置き換えてください
```

### GitHub PAT (任意)

もし `checkRisk.sh` がプライベートGitHubリポジトリにある場合は、以下のシークレットを作成します。デフォルトのシークレット名は `github/pat` です。

```sh
aws secretsmanager create-secret \
  --name "github/pat" \
  --secret-string '''{"token":"ghp_REPLACE-ME"}''' \
  --region ap-northeast-1 # <-- あなたのAWSリージョンに置き換えてください
```

## 3. アプリケーションの設定 (環境変数)

**ソースコードを編集する必要はありません。** すべての設定は環境変数を通じて行います。

シェルで直接設定するか、`checkrisk-cdk` ディレクトリに `.env` ファイルを作成して管理できます。

### `.env` ファイルの例:

`checkrisk-cdk` ディレクトリ内に `.env` という名前のファイルを作成し、以下の内容を記述します。**`SCRIPT_SOURCE_URL` は必ずあなたのスクリプトのURLに変更してください。**

```
# (必須) `checkRisk.sh` スクリプトのGitHub Raw URL。
# 同梱のENVファイルには下記の値が設定済みです。
SCRIPT_SOURCE_URL="https://raw.githubusercontent.com/shinkawamisaki/checkRisk/e3965152e0ee1ea80f10582e41e766dda30f3edd/checkRisk.sh"

# (任意) GPT要約機能を有効にします。"true" を設定します。
# POLISH_WITH_OPENAI="1"

# (任意) 手順2でデフォルト以外のシークレット名を使った場合は、ここで上書きします。
# SLACK_SECRET_NAME="my-slack-secret"
# OPENAI_SECRET_NAME="my-openai-secret"
# GITHUB_PAT_SECRET_NAME="my-github-secret"
```

## 4. デプロイ

1.  **依存関係のインストール**:
    ```sh
    npm install
    ```

2.  **AWS環境のブートストラップ** (アカウント/リージョンごとに一度だけ実行):
    ```sh
    cdk bootstrap
    ```

3.  **スタックのデプロイ**:
    プロジェクトが `.env` ファイルを自動的に読み込むように設定されています。以下のコマンドを実行するだけです。
    ```sh
    cdk deploy
    ```

## デプロイ後の運用

### 手動テスト

デプロイした環境の動作をすぐにテストしたい場合は、以下のコマンドで手動でプロセスをトリガーできます。
```sh
aws codebuild start-build --project-name aws-risk-weekly
```

### アンインストール

このプロジェクトで作成されたすべてのAWSリソースを削除するには、以下のコマンドを実行します。
```sh
cdk destroy
```
