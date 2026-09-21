<!--
SPDX-License-Identifier: LicenseRef-Shinkawa-NC-1.1
Copyright (c) 2025 Shinkawa
-->

# AWS Risk Weekly — AWS リスク週次チェックを Slack にやさしく通知する（CDK）

[checkRisk.sh](https://github.com/shinkawamisaki/checkRisk) を毎週月曜 9 時（JST）に AWS CodeBuild で自動実行し、
レポートを S3 に保存して Slack に通知するサーバーレス構成です。インフラは AWS CDK（TypeScript）で作ります。

対象は、スタートアップ〜シリーズ A 規模の「一人情シス」や情シス不在の会社。
毎週の点検を自動化しつつ、月曜の朝に威圧的な通知が並ばないように設計しています。

## 何が届くか

**成功時**（本文＋レポートの Markdown 添付）

```
✅ AWS Risk Weekly (123456789012) — 2026-09-21

そっとリマインド。週のはじまりです。

🟢 重大なリスクはありませんでした

- Critical:  0
- High:      0
- Medium:   1
- Low:      7
```

Critical があれば判定行が `🚨 クリティカルリスクあり。対応をお願いします。`、High があれば `⚠️ ハイリスク項目あり。対応を推奨します。` になります。
OpenAI 整形を有効にしていると、判定行の下に「今すぐ対応 Top5」がそのまま載ります。

**失敗時**（スクリプトの失敗・タイムアウト・停止、またはレポートが見つからないとき）

```
✅ AWS Risk Weekly (123456789012) — 2026-09-21

月曜の朝、ゆっくりスイッチ入れていきましょう。

⚠️ 今週のチェックは実行できませんでした（CodeBuild: FAILED）。
リスクの有無はまだ判定できていません。ログを確認してください。
- ビルド: `aws-risk-weekly:1a2b3c…`
- ログ: https://…（CloudWatch Logs）
```

「通知が来ない＝正常」にはしません。実行できなかった週もそれと分かる形で届きます。

## 構成

```
EventBridge (cron 月曜 00:00 UTC)
   └─▶ CodeBuild: checkRisk.sh を取得 → SHA-256 照合 → 実行 → レポートを S3 へ
           ├─ SUCCEEDED ─▶ EventBridge ─▶ Lambda ─▶ Slack（本文 + 添付）
           └─ FAILED 等 ─▶ EventBridge ─▶ Lambda ─▶ Slack（実行できませんでした）
```

| 役割 | 実装 | 責務 |
| --- | --- | --- |
| Runner | `lib/constructs/codebuild-runner.ts` | どう実行するか。起動ターゲットと「成功/失敗」のイベントパターンを提供する（`IRunner`） |
| Scheduler | `lib/constructs/schedule.ts` | いつ実行し、終わったらどう Notifier に渡すか。Runner の種類は知らない |
| Notifier | `lib/constructs/notifier.ts` + `lambda/lambda_function.py` | どう通知するか。レポート解析と Slack 投稿 |
| Storage | `lib/constructs/store.ts` | どこに保存するか。レポート保管バケット |

## 特徴

- **CodeBuild だけで完結**: 常駐するものが無く、週 1 回・数分の実行なので費用はほぼゼロ。EC2/ECS の管理権限も不要
- **失敗も通知**: SUCCEEDED だけでなく FAILED / FAULT / STOPPED / TIMED_OUT でも Slack に届く。成功イベントでも 24 時間以内のレポートが無ければ「見つかりません」と伝え、先週のレポートを今週の結果として流さない
- **圧のない通知**: タイトルの絵文字は固定、状態は判定行の 1 個だけ。挨拶文は 24 種を週替わりで
- **安全側の既定**: スクリプトはコミット固定 URL＋SHA-256 照合。CodeBuild は `SecurityAudit` と実際に使うシークレットだけ。レポートバケットは公開ブロック・TLS 必須・365 日で自動削除
- **デプロイに Docker 不要**: Lambda は標準ライブラリだけで書いてあり、バンドルが要らない
- **オフラインテスト付き**: CDK テンプレートのアサーション（jest）と、偽 Slack / 偽 S3 で Lambda を通すテスト（Python）。AWS にも Slack にも接続しない

## ファイル構成

```
bin/checkrisk-cdk.ts            CDK アプリのエントリ。.env（環境変数）を読んでスタックに渡す
lib/checkrisk-cdk-stack.ts      スタック本体。4 つのコンストラクトを組み合わせる
lib/constructs/runner.ts        IRunner インターフェース
lib/constructs/codebuild-runner.ts  CodeBuild 実装
lib/constructs/ecs-runner.ts    ECS 実装の骨組み（未実装）
lib/constructs/schedule.ts      EventBridge ルール（週次 cron / 成功 / 失敗）
lib/constructs/notifier.ts      Slack 通知 Lambda の定義
lib/constructs/store.ts         レポート保管バケット
lambda/lambda_function.py       Slack 通知 Lambda（標準ライブラリのみ）
assets/buildspec/buildspec.yml  CodeBuild の手順（取得 → 照合 → 実行 → アーティファクト）
test/checkrisk-cdk.test.ts      CDK テンプレートのテスト
test/test_lambda.py             Lambda のオフラインテスト
test/fixtures/                  checkRisk の期待レポートなど
.env.example                    設定の雛形（コピーして .env にする）
DEPLOY_GUIDE.md                 デプロイ手順
SPECIFICATION.md                仕様書
```

## 使い方

- **デプロイ手順** → [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)
- **仕様（通知フォーマット、イベント、設定項目）** → [SPECIFICATION.md](SPECIFICATION.md)

## テスト

```sh
npm test               # CDK テンプレート（jest）
npm run test:lambda    # Lambda（Python 3.10+、AWS/Slack への接続なし）
npm run test:all
```

## 外部スクリプトについて

このリポジトリは `SCRIPT_SOURCE_URL` で指定した外部のシェルスクリプト（例: 別リポジトリの `checkRisk.sh`）を実行します。
スクリプト本体はこのリポジトリに含まれていません。利用前に当該スクリプトのライセンスを確認し、条件に従ってください
（[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)）。

## ライセンス

リポジトリ内の [LICENCE](LICENCE) をご確認ください（非商用限定。自社向け利用は可）。
