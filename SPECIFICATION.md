<!--
SPDX-License-Identifier: LicenseRef-Shinkawa-NC-1.1
Copyright (c) 2025 Shinkawa
-->

# システム仕様書: AWS Risk Weekly (CDK)

## 1. 概要

指定したシェルスクリプト（`checkRisk.sh`）を週次で自動実行し、結果の要約を Slack に通知する AWS CDK アプリケーション。

### 1.1. 技術スタック

- **Infrastructure as Code:** AWS CDK v2（TypeScript）
- **実行環境:** AWS CodeBuild（`aws/codebuild/standard:8.0`、BUILD_GENERAL1_SMALL）
- **通知処理:** AWS Lambda（Python 3.13、外部ライブラリなし）
- **成果物保管:** Amazon S3
- **スケジュール実行・イベント連携:** Amazon EventBridge
- **認証情報管理:** AWS Secrets Manager

## 2. アーキテクチャ

役割ごとのコンストラクトを `CheckRiskStack`（`lib/checkrisk-cdk-stack.ts`）が組み合わせる。
実行環境は `IRunner` インターフェースで抽象化されており、`Scheduler` と `Notifier` は CodeBuild か ECS かを知らない。

### 2.1. `Storage`（`lib/constructs/store.ts`）

- `s3.Bucket` を 1 つ作る。名前は `<projectName>-<accountId>-<region>`
- バージョニング有効、SSE-S3、`enforceSSL`（TLS 以外を拒否）、公開アクセスは全ブロック
- ライフサイクル: 現行オブジェクトは `retentionDays`（既定 365）で削除、旧バージョンは 30 日、未完了マルチパートは 7 日で破棄
- `retain` が false（既定）のとき `RemovalPolicy.DESTROY` と `autoDeleteObjects`。true のとき `RETAIN`
- 出力: `bucket`

### 2.2. Runner

#### 2.2.1. `IRunner`（`lib/constructs/runner.ts`）

| プロパティ | 型 | 意味 |
| --- | --- | --- |
| `startTarget` | `events.IRuleTarget` | スケジュールルールから起動するためのターゲット |
| `runnerName` | `string` | 実行環境の一意な名前 |
| `successEventPattern` | `events.EventPattern` | 正常終了を表すイベントパターン |
| `failureEventPattern` | `events.EventPattern` | 異常終了（失敗・停止・タイムアウトなど）を表すイベントパターン |

#### 2.2.2. `CodeBuildRunner`（`lib/constructs/codebuild-runner.ts`）

- `codebuild.Project` と IAM ロールを作る。ソースは `assets/buildspec/` を S3 アセットとして渡す
- 入力: `projectName`, `sourceUrl`, `scriptSha256?`, `artifactBucket`, `polishWithOpenAi?`, `openAiSecretName?`, `githubPatSecretName?`
- CodeBuild の環境変数: `REPORTS_BUCKET`, `SRC_URL`, `SRC_SHA256`（指定時）, `POLISH_WITH_OPENAI`/`OPENAI_SECRET_NAME`（整形有効時）, `GITHUB_PAT_SECRET_NAME`（指定時）
- IAM: `SecurityAudit`、アーティファクトバケットの読み書き、`secretsmanager:GetSecretValue` は **OpenAI（整形有効時）と GitHub PAT（指定時）だけ**。Slack のシークレットは付与しない
- イベントパターン: `source=aws.codebuild`, `detail-type=CodeBuild Build State Change`, `project-name` 一致。成功は `build-status=SUCCEEDED`、失敗は `FAILED | FAULT | STOPPED | TIMED_OUT`

#### 2.2.3. `EcsRunner`（`lib/constructs/ecs-runner.ts`）

ECS/Fargate 実装の骨組み。未実装で、コンストラクタで例外を投げる。

### 2.3. `Notifier`（`lib/constructs/notifier.ts`）

- `lambda.Function`（`lambda/lambda_function.py`、`Code.fromAsset`、バンドルなし）と IAM ロール、ロググループ（保持 1 か月）を作る
- 環境変数: `S3_BUCKET`, `S3_PREFIX`（空）, `SLACK_SECRET_NAME`, `MAX_REPORT_AGE_HOURS`（既定 24）, `POLISH_WITH_OPENAI`（整形有効時のみ `true`）
- IAM: `AWSLambdaBasicExecutionRole`、アーティファクトバケットの読取、Slack シークレットの `GetSecretValue`
- 出力: `func`

### 2.4. `Scheduler`（`lib/constructs/schedule.ts`）

EventBridge ルールを 3 つ作る。

| ルール | 条件 | ターゲット |
| --- | --- | --- |
| `<projectName>-weekly-cron` | `cron(0 0 ? * MON *)`（月曜 00:00 UTC = JST 09:00）。`schedule` で変更可 | `runner.startTarget` |
| `<projectName>-on-success` | `runner.successEventPattern` | Notifier Lambda（`outcome: "success"`） |
| `<projectName>-on-failure` | `runner.failureEventPattern` | Notifier Lambda（`outcome: "failure"`） |

Lambda への入力は InputTransformer で次の形にする。`detail` は元イベントの `detail` をそのまま埋め込む。

```json
{ "outcome": "success" | "failure", "runner": "<runnerName>", "detail": { ...元イベントの detail... } }
```

再試行は 1 回、イベントの最大保持は 2 時間（既定の 185 回/24 時間だと Slack 側の一時障害で同じ通知が繰り返されるため）。

## 3. CodeBuild の処理（`assets/buildspec/buildspec.yml`）

1. `jq` と `curl` が無ければ apt で入れる（標準イメージには入っている）
2. `GITHUB_PAT_SECRET_NAME` が設定されていれば PAT を取得し（文字列そのもの、または `{"token": ...}`）、`Authorization: token` 付きで `SRC_URL` を取得。取得後に PAT は unset する
3. `SRC_SHA256` が設定されていれば `sha256sum -c` で照合し、不一致なら exit 3
4. `bash ./checkRisk.sh` を実行。OpenAI の API キーは buildspec では扱わない（checkRisk.sh が整形有効時に自分で Secrets Manager から読む）
5. `output/checkRiskReport_*.md` をカレントに移し、アーティファクト（`checkRiskReport_*.md`）としてバケット直下に置く

## 4. 設定項目

| 変数（.env） | 既定 | 用途 |
| --- | --- | --- |
| `SCRIPT_SOURCE_URL` | （必須） | 実行するスクリプトの Raw URL。コミット SHA かタグで固定 |
| `SCRIPT_SHA256` | なし | スクリプトの SHA-256。16 進 64 桁。指定時は照合 |
| `POLISH_WITH_OPENAI` | `0` | `1`/`true` で OpenAI 整形 |
| `SLACK_SECRET_NAME` | `slack/bot` | `{"bot_token": "...", "channel_id": "..."}` を格納したシークレット |
| `OPENAI_SECRET_NAME` | `openai/prod/key` | API キー文字列そのものを格納したシークレット |
| `GITHUB_PAT_SECRET_NAME` | なし | 指定時のみ PAT を取得 |
| `REPORT_RETENTION_DAYS` | `365` | レポート保持日数 |
| `RETAIN_BUCKET` | `0` | `1` でバケットを残す |

## 5. レポートファイル

checkRisk.sh が生成する `checkRiskReport_<YYYYMMDD_HHMMSS>.md`（JST）をそのままのキーでバケット直下に保存する。
OpenAI 整形が有効なときは `checkRiskReport_<YYYYMMDD_HHMMSS>_polished.md` も並ぶ。バージョニングとライフサイクルで履歴を管理する。

## 6. Slack 通知（`lambda/lambda_function.py`）

### 6.1. 処理の流れ

1. 入力の `outcome` を読む（無ければ `detail.build-status` から推定。`{}` で手動起動したときは success 扱い）
2. **failure** なら「実行できませんでした」を 1 通投稿して終了
3. **success** なら S3 の最新レポート（`LastModified` 最大）を探す。無い、または `MAX_REPORT_AGE_HOURS` より古ければ「今週のレポートが見つかりません」を投稿して終了
4. 元レポートから `## サマリー` の件数を読む。`POLISH_WITH_OPENAI` が有効で `_polished.md` があれば添付をそれに替え、Top5 を抽出する
5. 本文を投稿し、続けてレポートを添付する。添付だけ失敗したときは例外にせず、短い追記を投稿して終了する（EventBridge の再試行で本文が二重投稿されないように）

### 6.2. Slack API

標準ライブラリ（`urllib`）で `chat.postMessage`、`files.getUploadURLExternal` → アップロード URL への POST → `files.completeUploadExternal` を呼ぶ。
Bot に必要なスコープは `chat:write` と `files:write`。`icon_emoji` の反映には `chat:write.customize` が要る（無ければ無視される）。

### 6.3. 成功時の本文

1. **タイトル**: `✅ AWS Risk Weekly (<AccountId>) — <YYYY-MM-DD>`（日付は JST）。絵文字は状態に関わらず固定
2. **挨拶文**: 24 種の固定リストから週替わりで 1 つ。基準日 2025-09-29（月）からの経過週数 `% 24` で選ぶ（暦年に依存しないので年末年始で同じ挨拶が続かない）
3. **判定行**（太字）: Critical ≥ 1 → `🚨 クリティカルリスクあり。対応をお願いします。` / High ≥ 1 → `⚠️ ハイリスク項目あり。対応を推奨します。` / それ以外 → `🟢 重大なリスクはありませんでした`
4. **件数**: `- Critical / High / Medium / Low`（常に元レポートから読む）
5. **Top5**（あれば）: 見出し `### … 今すぐ対応 … Top5 …` の行から次の `#`/`##` 見出しまで。checkRisk の旧見出し `### ■ 今すぐ対応 Top5 ■` と新見出し `### 🔴 今すぐ対応（Top5）` の両方に対応
6. **添付**: レポートの Markdown。コメントは `:memo: レポート（Markdown）を添付します。`

### 6.4. 失敗時の本文

タイトルと挨拶は成功時と同じ。判定行は `⚠️ 今週のチェックは実行できませんでした（<理由>）。` で、続けて「リスクの有無はまだ判定できていません」、ビルド ID、CloudWatch Logs のリンク（イベントに含まれる場合）を載せる。添付は無い。

理由は `CodeBuild: FAILED` のような実行状態、または `S3 に今週のレポートが見つかりません。最新は 2026-09-14 09:03`。

## 7. テスト

- `npm test`: `aws-cdk-lib/assertions` でテンプレートを検証（スケジュール、ルールと InputTransformer、IAM の範囲、環境変数、ランタイム/イメージ、バケット設定、Runner の差し替え）
- `npm run test:lambda`: Python の `unittest`。レポート解析・判定・挨拶ローテーションに加え、ローカルの偽 Slack サーバーと偽 S3 でハンドラ全体を通す。AWS にも Slack にも接続しない
