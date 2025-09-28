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

このように「現状の要件に最適化しつつ、将来の拡張に備える」ことを意識した設計になっています。

## License

This repository is licensed under the [Apache License 2.0](./LICENSE).  
© 2025 Shinkawa.
