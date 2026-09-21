<!--
SPDX-License-Identifier: LicenseRef-Shinkawa-NC-1.1
Copyright (c) 2025 Shinkawa
-->

# AWS Risk Weekly (CDK) — デプロイガイド

> **注意:** `SCRIPT_SOURCE_URL` で指定するシェルスクリプトは**別リポジトリの外部資産**です。利用前に必ず当該スクリプトのライセンスを確認し、条件に従ってください。

実行フローは **EventBridge → CodeBuild → S3 → EventBridge → Lambda → Slack** です。

- **既定のスケジュール**: 毎週 **月曜 00:00 UTC**（JST 09:00）。変えたい場合は `lib/checkrisk-cdk-stack.ts` の `Scheduler` に `schedule` を渡してください

## 前提条件

- AWS アカウントと AWS CLI（デプロイする人に IAM / S3 / Lambda / CodeBuild / EventBridge の作成権限）
- Node.js 18 以上（20 以上を推奨）と npm
- **Docker は不要**です（Lambda は標準ライブラリだけで書いてあり、バンドルしません）
- macOS / Linux / WSL2 で確認。Windows ネイティブでも `npm` と `aws` が動けば可

## 1. Secrets Manager にシークレットを作る

### 必須: Slack Bot

1. Slack アプリを作成し、Bot Token Scopes に `chat:write` と `files:write` を付ける
   （投稿アイコンを ✅ にしたい場合は `chat:write.customize` も。無くても動きます）
2. ワークスペースにインストールして **Bot User OAuth Token**（`xoxb-...`）を控える
3. 通知先チャンネルにアプリを招待し、**チャンネル ID**（`C...`）を控える

```sh
aws secretsmanager create-secret \
  --name "slack/bot" \
  --secret-string '{"bot_token":"<BOT_TOKEN>","channel_id":"<CHANNEL_ID>"}' \
  --region <REGION>
```

### 任意: OpenAI（レポート整形）

値は **API キーの文字列そのもの**を入れます（checkRisk の README と同じ形式。JSON では動きません）。

```sh
aws secretsmanager create-secret \
  --name "openai/prod/key" \
  --secret-string "sk-xxxxxxxxxxxxxxxxxxxx" \
  --region <REGION>
```

### 任意: GitHub PAT（私有リポジトリからスクリプトを取得する場合だけ）

値は PAT の文字列そのもの、または `{"token":"<GITHUB_PAT>"}` のどちらでも可。

```sh
aws secretsmanager create-secret \
  --name "github/pat" \
  --secret-string "<GITHUB_PAT>" \
  --region <REGION>
```

## 2. 設定（.env）

ソースコードの改変は不要です。`.env.example` をコピーして `.env` を作り、値を入れます。`.env` は Git に含めません。

```sh
cp .env.example .env
```

| 変数 | 必須 | 説明 |
| --- | --- | --- |
| `SCRIPT_SOURCE_URL` | ✅ | 実行するスクリプトの Raw URL。**コミット SHA かタグで固定**する（ブランチ名だと実行内容が黙って変わる） |
| `SCRIPT_SHA256` | 推奨 | そのスクリプトの SHA-256。CodeBuild がダウンロード後に照合し、不一致なら実行しない。`curl -fsSL "$SCRIPT_SOURCE_URL" \| shasum -a 256` で計算 |
| `POLISH_WITH_OPENAI` | | `1` で OpenAI 整形を有効化。既定は無効 |
| `SLACK_SECRET_NAME` | | 既定 `slack/bot` |
| `OPENAI_SECRET_NAME` | | 既定 `openai/prod/key` |
| `GITHUB_PAT_SECRET_NAME` | | 設定したときだけ PAT を取得する。公開リポジトリなら未設定のまま |
| `REPORT_RETENTION_DAYS` | | S3 のレポート保持日数。既定 365 |
| `RETAIN_BUCKET` | | `1` で `cdk destroy` 時にバケットを残す。既定は削除 |

同梱の `.env.example` は checkRisk の固定コミットと SHA-256 が設定済みです。

## 3. デプロイ

```sh
npm install
npx cdk bootstrap      # 初回のみ（アカウント/リージョンごと）
npx cdk deploy
```

`.env` は自動で読み込まれます。

## 4. 動作確認

すぐ試すには CodeBuild を手動実行します。数分後に Slack に本文と添付が届けば成功です。

```sh
aws codebuild start-build --project-name aws-risk-weekly
```

失敗通知も確認しておくと安心です。存在しない URL を渡すと取得に失敗し、「実行できませんでした（CodeBuild: FAILED）」が届きます。

```sh
aws codebuild start-build --project-name aws-risk-weekly \
  --environment-variables-override name=SRC_URL,value=https://example.invalid/none.sh,type=PLAINTEXT
```

詳細ログは CloudWatch Logs（`/aws/codebuild/aws-risk-weekly`、`/aws/lambda/aws-risk-weekly-slack`）にあります。

## 5. checkRisk を更新するとき

1. checkRisk の新しいコミット SHA で `SCRIPT_SOURCE_URL` を書き換える
2. `SCRIPT_SHA256` を計算し直す
3. `npx cdk deploy`

## クリーンアップ

```sh
npx cdk destroy
```

既定ではレポートバケットも中身ごと削除されます。残したい場合は `.env` に `RETAIN_BUCKET=1` を設定してからデプロイしておいてください。

## 旧版（2025-09 公開時点）からの移行

| 変更 | やること |
| --- | --- |
| OpenAI シークレットの形式が JSON からキー文字列そのものに | `aws secretsmanager put-secret-value --secret-id openai/prod/key --secret-string "sk-..."` で入れ直す |
| GitHub PAT が任意（既定で取得しない）に | 私有リポジトリを使う場合だけ `.env` に `GITHUB_PAT_SECRET_NAME` を設定 |
| `.env` がリポジトリに含まれなくなった | `.env.example` をコピーして作る |
| Docker が不要に、Lambda ランタイムが Python 3.13 に、CodeBuild が standard:8.0 に | `npm install` して `npx cdk deploy`。既存リソースはそのまま更新される |
| レポートバケットにライフサイクル（既定 365 日）が付いた | 1 年より前のレポートを残したい場合は先に `REPORT_RETENTION_DAYS` を大きくする |
| 失敗ルールが増えた | 何もしなくてよい。失敗した週は「実行できませんでした」が届く |

## トラブルシューティング

- **`SCRIPT_SOURCE_URL is not set`** → `.env` が無いか値が空。`.env.example` をコピー
- **Slack に「実行できませんでした（CodeBuild: FAILED）」** → CodeBuild のログを確認。SHA-256 不一致（exit 3）なら `SCRIPT_SHA256` を計算し直す
- **「S3 に今週のレポートが見つかりません」** → CodeBuild は成功したがアーティファクトが無い。buildspec の `mv output/checkRiskReport_*.md .` 以降のログを確認
- **添付だけ失敗した** → Bot に `files:write` があるか、チャンネルにアプリが招待されているかを確認
- **ブートストラップ未実施** → `npx cdk bootstrap`
- **リージョン/認証不整合** → `aws ... --region <REGION>` と認証プロファイルを統一

## ライセンス

リポジトリ内の [LICENCE](LICENCE) をご確認ください。
