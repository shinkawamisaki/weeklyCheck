<!--
SPDX-License-Identifier: LicenseRef-NC-Shinkawa-Only
Copyright (c) 2025 Shinkawa
-->

<!--
Copyright (c) 2025 Shinkawa
-->

# システム仕様書: AWS Risk Weekly CDK

## 1. 概要

本システムは、指定されたシェルスクリプト (`checkRisk.sh`) を週次で自動実行し、結果の要約をSlackに通知することを目的とした、AWS CDKによるサーバーレスアプリケーションです。

### 1.1. 技術スタック

- **Infrastructure as Code:** AWS CDK (TypeScript)
- **実行環境:** AWS CodeBuild (ECS/Fargateなどへの拡張を想定した設計)
- **通知処理:** AWS Lambda (Python 3.11)
- **成果物保管:** Amazon S3
- **スケジュール実行 & イベント連携:** Amazon EventBridge
- **認証情報管理:** AWS Secrets Manager

## 2. アーキテクチャ

本システムは、将来的な機能変更や拡張を容易にするため、役割ごとにコンポーネント化されたCDKコンストラクトで構築されています。特に、スクリプト実行環境は`IRunner`インターフェースによって抽象化されており、`CodeBuildRunner`や`EcsRunner`といった具体的な実装を容易に切り替えられる設計になっています。

メインのCDKスタック (`CheckRiskStack`) が、これらのコンストラクトを組み合わせてインフラ全体を構築します。

### 2.1. `Storage` コンストラクト

- **ファイル:** `lib/constructs/store.ts`
- **役割:** レポートなどの成果物を保管するS3バケットを作成します。
- **リソース:**
    - `s3.Bucket`: 成果物保管用のS3バケット。
- **主な仕様:**
    - オブジェクトのバージョン管理: 有効。
    - サーバーサイド暗号化: 有効 (AES-256)。
    - スタック削除時の自動削除: 有効 (デモ・開発用設定)。
- **出力 (Public Properties):**
    - `bucket: s3.Bucket`: 作成されたS3バケットのインスタンス。他のコンストラクトが参照するために公開されます。

### 2.2. 実行環境 (Runner)

#### 2.2.1. `IRunner` インターフェース
- **ファイル:** `lib/constructs/runner.ts`
- **役割:** スクリプト実行環境の共通インターフェースを定義します。これにより、`Scheduler`は具体的な実行環境（CodeBuild, ECSなど）を意識することなく、処理をトリガーできます。
- **インターフェースの主なプロパティ:**
    - `startTarget: events.IRuleTarget`: EventBridgeが実行を開始するためのターゲット。
    - `runnerName: string`: イベントフィルタリングに使用される、実行環境の一意な名前。

#### 2.2.2. `CodeBuildRunner` コンストラクト
- **ファイル:** `lib/constructs/codebuild-runner.ts`
- **役割:** `IRunner`インターフェースのCodeBuild実装。`checkRisk.sh` をダウンロードし、クリーンなサーバーレス環境で実行します。
- **リソース:**
    - `codebuild.Project`: スクリプトの実行環境となるCodeBuildプロジェクト。
    - `iam.Role`: CodeBuildプロジェクトに割り当てるIAMロール。
- **入力 (Props):**
    - `artifactBucket: s3.Bucket`: `Storage`コンストラクトが作成したS3バケット。
    - `sourceUrl: string`: 実行対象である `checkRisk.sh` のURL。
    - `slackSecretName`, `openAiSecretName`, `githubPatSecretName`: (任意) Secrets Managerから認証情報を取得するためのシークレット名。
- **IAMロール権限:**
    - `SecurityAudit` (AWSマネージドポリシー)。
    - `artifactBucket` に対するS3読み書き権限。
    - 各種Secretに対する `secretsmanager:GetSecretValue` 権限。

### 2.3. `Notifier` コンストラクト

- **ファイル:** `lib/constructs/notifier.ts`
- **役割:** S3に保存されたレポートを解析し、整形した上でSlackに通知します。
- **リソース:**
    - `lambda.Function`: Pythonで記述されたLambda関数。
    - `iam.Role`: Lambda関数に割り当てるIAMロール。
    - `logs.LogGroup`: Lambda関数のロググループ。
- **入力 (Props):**
    - `artifactBucket: s3.Bucket`: レポートが保管されているS3バケット。
    - `slackSecretName: string`: Slack認証情報が格納されているシークレット名。
- **出力 (Public Properties):**
    - `func: lambda.IFunction`: 作成されたLambda関数のインスタンス。`Scheduler`がターゲットとして参照するために公開されます。
- **IAMロール権限:**
    - `AWSLambdaBasicExecutionRole` (AWSマネージドポリシー)。
    - `artifactBucket` に対するS3読み取り権限。
    - `slackSecretName` に対する `secretsmanager:GetSecretValue` 権限。

### 2.4. `Scheduler` コンストラクト

- **ファイル:** `lib/constructs/schedule.ts`
- **役割:** システム全体の実行を自動化し、コンポーネント間を連携させます。
- **リソース:**
    - `events.Rule` (2つ): スケジュール実行とイベント駆動を実現するEventBridgeルール。
- **入力 (Props):**
    - `runner: IRunner`: `CodeBuildRunner`など、`IRunner`インターフェースを実装した実行環境のインスタンス。
    - `notifierFunction: lambda.IFunction`: `Notifier`が作成したLambda関数。
- **ルール詳細:**
    - **週次実行ルール:** 毎週月曜日の00:00 (UTC) に `runner.startTarget` をトリガーします。
    - **成功時ルール:** `runner` の実行が `SUCCEEDED` になったことを検知（`runner.runnerName`でフィルタリング）し、`notifierFunction` をトリガーします。

## 3. プロジェクトファイル構造

- `bin/checkrisk-cdk.ts`: CDKアプリケーションのエントリーポイント。
- `lib/checkrisk-cdk-stack.ts`: メインのCDKスタック。各コンストラクトを組み合わせてインフラ全体を定義します。
- `lib/constructs/`: 再利用可能なコンストラクト（部品）を格納するディレクトリ。
    - `runner.ts`: `IRunner`インターフェースの定義。
    - `codebuild-runner.ts`: `IRunner`のCodeBuild実装。
    - `ecs-runner.ts`: 将来的なECS実装のためのスケルトン。
    - `notifier.ts`: Slack通知Lambdaを定義するコンストラクト。
    - `schedule.ts`: EventBridgeルールを定義するコンストラクト。
    - `store.ts`: S3バケットを定義するコンストラクト。
- `assets/buildspec/buildspec.yml`: CodeBuildが実行するビルドコマンドを定義したファイル。
- `lambda/`: Lambda関数のPythonソースコードと依存関係ファイルを格納するディレクトリ。
- `DEPLOY_GUIDE.md`: プロジェクトのデプロイ手順書。
- `SPECIFICATION.md`: このドキュメントです。

## 4. 設定項目

本システムのデプロイと実行には、いくつかの事前設定が必要です。詳細は `DEPLOY_GUIDE.md` を参照してください。

- **AWS Secrets Manager:**
    - `slack/bot`: SlackのBotトークンとチャンネルIDを格納する必須のシークレット。
    - `openai/prod/key`: (任意) OpenAIのAPIキーを格納するシークレット。
    - `github/pat`: (任意) プライベートリポジトリ用のGitHub PATを格納するシークレット。
- **CDK設定ファイル (`bin/checkrisk-cdk.ts`):**
    - `SCRIPT_SOURCE_URL`: 実行対象である `checkRisk.sh` のGitHub Raw URL。
    - 上記シークレットの名前（デフォルトから変更した場合）。

## 5. レポートファイルの命名規則

S3に保存されるレポートファイルは、`report_YYYYMMDD.md` (例: `report_20250925.md`) という形式で保存されます。これにより、過去のレポートが上書きされることなく、履歴として蓄積されます。

## 6. 機能仕様

### 6.1. Slack通知

Lambda関数によって送信されるSlack通知は、以下の仕様に基づいています。

#### 6.1.1. 全体構成

メッセージは、以下の要素で構成されます。

1.  **タイトル**
2.  **挨拶文**
3.  **判定メッセージ**（太字）
4.  **件数サマリー**
5.  **Top5 ブロック**（存在する場合のみ）
6.  **添付ファイル**

#### 6.1.2. 各要素の詳細

-   **タイトル**:
    -   フォーマット: `✅ AWS Risk Weekly (<AccountId>) — <YYYY-MM-DD>`
    -   日付はUTC基準で生成されます。

-   **挨拶文**:
    -   JST（日本標準時）を基準に、週替わりで24種類の固定リストから1つが選ばれます。
    -   ローテーションロジック: `(JSTの年間通算日 - 1) // 7 % 24`

-   **判定メッセージ**:
    -   リスクのレベルに応じて、以下のメッセージが**太字**で表示されます。
        -   Critical ≥ 1: `*🚨 クリティカルリスクあり。対応をお願いします。*`
        -   High ≥ 1 (かつ Critical==0): `*⚠️ ハイリスク項目あり。対応を推奨します。*`
        -   上記以外: `*🟢 重大なリスクはありませんでした*`

-   **Top5 ブロック**:
    -   `checkRisk.sh` が生成したレポート（`_polished.md` または `*.md`）から、見出しと内容がそのまま抽出されて表示されます。
    -   抽出される見出し: `### ■ 今すぐ対応 Top5 ■`

-   **添付ファイル**:
    -   レポートのMarkdownファイルが添付されます。
    -   添付ファイルのコメント: `:memo: レポート（Markdown）を添付します。`

### 6.2. レポート生成 (`checkRisk.sh`)

#### 6.2.1. OpenAIによる整形

-   `POLISH_WITH_OPENAI=true` の場合、OpenAI APIを利用してレポートの整形を試みます。
-   **プロンプトの指示**:
    -   `### ■ 今すぐ対応 Top5 ■` という見出しでサマリーを生成するように指示します。
    -   **文字化けを防ぐため、AIが絵文字を一切使用しないように、明示的に指示しています。**

