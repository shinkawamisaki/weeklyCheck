<!--
SPDX-License-Identifier: LicenseRef-NC-Shinkawa-Only
Copyright (c) 2025 Shinkawa
-->

<!--
Copyright (c) 2025 Shinkawa
-->

# AWSリスク週次レポート Slack通知システム

## 概要

このプロジェクトは、指定されたシェルスクリプト (`checkRisk.sh`) を週次で自動実行し、その結果をSlackに通知するサーバーレスアプリケーションです。

インフラの管理には AWS CDK (TypeScript) を使用しており、サーバーレスアーキテクチャで構築されています。

## 主な機能

*   **週次自動実行**: Amazon EventBridgeにより、毎週定時にスクリプトを自動実行します。
*   **柔軟なスクリプト実行**: AWS CodeBuildを利用し、GitHubなどにある任意のシェルススクリプトを実行できます。
*   **AIによるレポート整形**: OpenAI APIと連携し、実行結果のレポートをAIが要約・整形する機能を持ちます。（ON/OFF可能）
*   **Slack通知**: 実行結果のサマリーと、完全なレポート（Markdownファイル）をSlackに通知します。

## ファイル構成

*   `checkRisk.sh`: 実際に監査を行うシェルススクリプトのサンプルです。
*   `checkrisk-cdk/`: AWSインフラを定義・管理するCDKプロジェクトです。
    *   `lib/checkrisk-cdk-stack.ts`: インフラ定義の本体です。
    *   `lambda/`: Slack通知を行うLambda関数のソースコードです。
*   `DEPLOY_GUIDE.md`: 詳細なデプロイ手順書です。
*   `SPECIFICATION.md`: このシステムの詳細な仕様書です。

## 利用方法

詳細なセットアップとデプロイの手順については、以下のドキュメントを参照してください。

- **詳細なデプロイ手順はこちら → [デプロイガイド (DEPLOY_GUIDE.md)](DEPLOY_GUIDE.md)**

## Third-Party / External Scripts

This system can execute an external shell script specified via `SCRIPT_SOURCE_URL`
(for example, a separate repository’s `checkRisk.sh`). That script is **not**
distributed with this repository. Please review and comply with that script’s
license before use.

## License

This repository (infrastructure code, Lambda code, and docs) is licensed under **Apache License 2.0** (see `./LICENSE`).

*Note:* Any external script executed via `SCRIPT_SOURCE_URL` (e.g., `checkRisk.sh` in another repository) is licensed **separately** under its own terms.

