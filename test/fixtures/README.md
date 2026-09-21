# テスト用フィクスチャ

- `report_sample.md` / `report_empty.md`: checkRisk（https://github.com/shinkawamisaki/checkRisk）の
  オフラインテストが生成する期待レポート（`tests/golden/`）のコピー。指摘が多いアカウントと指摘ゼロのアカウント。
- `report_polished_new_heading.md`: OpenAI 整形後レポートの形（checkRisk 27c9a9c 以降の見出し `### 🔴 今すぐ対応（Top5）`）。
- `report_polished_old_heading.md`: 同上、旧見出し `### ■ 今すぐ対応 Top5 ■`（checkRisk e396515 まで）。
