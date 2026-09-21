"""Slack 通知 Lambda のオフラインテスト。

AWS にも Slack にも接続せず、レポート解析・判定・挨拶ローテーションを検証する。
実行: npm run test:lambda（または python3 -m unittest discover -s test -p 'test_*.py'）
"""
import os
import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

# Lambda モジュールが import 時に要求する外部依存と環境変数をダミーで満たす
for name in ("boto3", "botocore", "botocore.exceptions", "slack_sdk"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["boto3"].client = lambda *a, **k: None
sys.modules["botocore.exceptions"].ClientError = Exception
sys.modules["slack_sdk"].WebClient = object
os.environ.setdefault("S3_BUCKET", "dummy-bucket")
os.environ.setdefault("SLACK_SECRET_NAME", "slack/bot")
sys.path.insert(0, str(HERE.parent / "lambda"))
import lambda_function as lf  # noqa: E402


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class SummaryParsing(unittest.TestCase):
    def test_counts_from_sample_report(self):
        lines = lf._extract_original_summary(fixture("report_sample.md"))
        self.assertEqual(lf._parse_counts(lines), {"Critical": 1, "High": 17, "Medium": 9, "Low": 8})

    def test_counts_from_empty_report(self):
        lines = lf._extract_original_summary(fixture("report_empty.md"))
        self.assertEqual(lf._parse_counts(lines), {"Critical": 0, "High": 0, "Medium": 1, "Low": 7})

    def test_missing_summary_gives_no_lines(self):
        self.assertEqual(lf._extract_original_summary(b"# nothing here\n"), [])


class RiskBanner(unittest.TestCase):
    def test_critical_wins(self):
        self.assertIn("🚨", lf._risk_banner({"Critical": 1, "High": 5, "Medium": 0, "Low": 0}))

    def test_high_without_critical(self):
        self.assertIn("⚠️", lf._risk_banner({"Critical": 0, "High": 1, "Medium": 0, "Low": 0}))

    def test_medium_and_low_only_is_green(self):
        self.assertIn("🟢", lf._risk_banner({"Critical": 0, "High": 0, "Medium": 3, "Low": 9}))


class Top5Extraction(unittest.TestCase):
    def test_new_heading_from_checkrisk_27c9a9c(self):
        block = lf._extract_top5_block(fixture("report_polished_new_heading.md"))
        self.assertTrue(block.startswith("### 🔴 今すぐ対応（Top5）"))
        self.assertIn("5. GuardDuty が未有効化", block)
        self.assertNotIn("AWSセキュリティ監査レポート", block)  # 次の見出しで止まる

    def test_old_heading_from_checkrisk_e396515(self):
        block = lf._extract_top5_block(fixture("report_polished_old_heading.md"))
        self.assertTrue(block.startswith("### ■ 今すぐ対応 Top5 ■"))
        self.assertIn("2. root にアクセスキーが存在", block)
        self.assertNotIn("サマリー", block)

    def test_original_report_has_no_top5(self):
        self.assertEqual(lf._extract_top5_block(fixture("report_sample.md")), "")


class GreetingRotation(unittest.TestCase):
    def mondays(self, start: date, n: int):
        return [start + timedelta(weeks=i) for i in range(n)]

    def test_24_weeks_are_all_different_then_repeat(self):
        picks = [lf.pick_greeting(lf.GREETINGS, d) for d in self.mondays(lf.GREETING_EPOCH, 25)]
        self.assertEqual(len(set(picks[:24])), 24)
        self.assertEqual(picks[24], picks[0])

    def test_no_repeat_across_new_year(self):
        # 旧実装（年間通算日ベース）では 12 月第 2 週〜1 月第 4 週で同じ 4 本が続いていた
        picks = [lf.pick_greeting(lf.GREETINGS, d) for d in self.mondays(date(2026, 12, 7), 8)]
        self.assertEqual(len(set(picks)), 8)

    def test_same_week_gives_same_greeting(self):
        monday = date(2026, 9, 21)
        self.assertEqual(lf.pick_greeting(lf.GREETINGS, monday), lf.pick_greeting(lf.GREETINGS, monday + timedelta(days=6)))


class MessageBuilders(unittest.TestCase):
    ACCOUNT = "123456789012"
    TODAY = date(2026, 9, 21)

    def test_success_message_has_title_greeting_banner_counts_and_top5(self):
        lines = lf._extract_original_summary(fixture("report_sample.md"))
        top5 = lf._extract_top5_block(fixture("report_polished_new_heading.md"))
        body = lf.build_success_message(self.ACCOUNT, self.TODAY, lines, top5, "おはよう")
        self.assertTrue(body.startswith(":white_check_mark: AWS Risk Weekly (123456789012) — 2026-09-21"))
        self.assertIn("おはよう", body)
        self.assertIn("🚨 クリティカルリスクあり", body)
        self.assertIn("- Critical:  1", body)
        self.assertIn("### 🔴 今すぐ対応（Top5）", body)

    def test_success_message_without_summary_says_so(self):
        body = lf.build_success_message(self.ACCOUNT, self.TODAY, [], "", "おはよう")
        self.assertIn("🟢 重大なリスクはありませんでした", body)
        self.assertIn("サマリーを抽出できませんでした", body)
        self.assertNotIn("今すぐ対応", body)

    def test_failure_message_keeps_fixed_title_and_says_unknown(self):
        body = lf.build_failure_message(self.ACCOUNT, self.TODAY, "おはよう", "CodeBuild: FAILED",
                                        build_id="arn:aws:codebuild:ap-northeast-1:123456789012:build/aws-risk-weekly:abc-123",
                                        log_url="https://console.aws.amazon.com/cloudwatch/x")
        self.assertTrue(body.startswith(":white_check_mark: AWS Risk Weekly (123456789012) — 2026-09-21"))
        self.assertIn("⚠️ 今週のチェックは実行できませんでした（CodeBuild: FAILED）", body)
        self.assertIn("判定できていません", body)
        self.assertIn("`aws-risk-weekly:abc-123`", body)
        self.assertIn("https://console.aws.amazon.com/cloudwatch/x", body)
        self.assertNotIn("🚨", body)
        self.assertNotIn("🟢", body)


class OutcomeDetection(unittest.TestCase):
    def test_outcome_from_rule_input(self):
        self.assertEqual(lf._outcome_of({"outcome": "failure", "detail": {"build-status": "FAILED"}})[0], "failure")
        self.assertEqual(lf._outcome_of({"outcome": "success", "detail": {"build-status": "SUCCEEDED"}})[0], "success")

    def test_outcome_inferred_from_raw_codebuild_event(self):
        self.assertEqual(lf._outcome_of({"detail": {"build-status": "TIMED_OUT"}})[0], "failure")
        self.assertEqual(lf._outcome_of({"detail": {"build-status": "SUCCEEDED"}})[0], "success")

    def test_manual_invocation_with_empty_event_is_success(self):
        self.assertEqual(lf._outcome_of({})[0], "success")


if __name__ == "__main__":
    unittest.main()
