"""Slack 通知 Lambda のオフラインテスト。

AWS にも Slack にも接続せず、レポート解析・判定・挨拶ローテーションを検証する。
実行: npm run test:lambda（または python3 -m unittest discover -s test -p 'test_*.py'）
"""
import io
import json
import os
import sys
import threading
import types
import unittest
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

# Lambda モジュールが import 時に要求する boto3 と環境変数をダミーで満たす（Lambda 実行環境には同梱されている）
for name in ("boto3", "botocore", "botocore.exceptions"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["boto3"].client = lambda *a, **k: None


class _FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


sys.modules["botocore.exceptions"].ClientError = _FakeClientError
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


# ----- 偽 Slack サーバー（Web API の 3 メソッド + アップロード URL） ----------------------
class FakeSlack:
    """受け取ったリクエストを記録し、Slack Web API 風の JSON を返すローカル HTTP サーバー。"""

    def __init__(self, fail_upload: bool = False):
        self.requests: list[dict] = []
        self.fail_upload = fail_upload
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # 静かに
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                ctype = self.headers.get("Content-Type", "")
                if ctype.startswith("application/json"):
                    body = json.loads(raw)
                elif ctype.startswith("application/x-www-form-urlencoded"):
                    body = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
                else:
                    body = raw
                fake.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "ctype": ctype, "body": body})
                if self.path == "/api/chat.postMessage":
                    out = {"ok": True, "ts": "1.2"}
                elif self.path == "/api/files.getUploadURLExternal":
                    out = {"ok": True, "upload_url": f"http://127.0.0.1:{fake.port}/upload/abc", "file_id": "F123"}
                elif self.path == "/upload/abc":
                    if fake.fail_upload:
                        self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
                    self.send_response(200); self.end_headers(); self.wfile.write(b"OK - 123"); return
                elif self.path == "/api/files.completeUploadExternal":
                    out = {"ok": True, "files": [{"id": "F123"}]}
                else:
                    out = {"ok": False, "error": "unknown_method"}
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()

    def client(self):
        return lf.SlackClient("xoxb-test", base_url=f"http://127.0.0.1:{self.port}/api/")

    def paths(self):
        return [r["path"] for r in self.requests]


class SlackClientTests(unittest.TestCase):
    def test_post_message_sends_json_with_bearer_token(self):
        with FakeSlack() as fake:
            fake.client().chat_postMessage(channel="C1", text="hello", icon_emoji=":white_check_mark:")
            self.assertEqual(fake.paths(), ["/api/chat.postMessage"])
            r = fake.requests[0]
            self.assertEqual(r["auth"], "Bearer xoxb-test")
            self.assertEqual(r["body"], {"channel": "C1", "text": "hello", "icon_emoji": ":white_check_mark:"})

    def test_upload_follows_three_step_external_upload_flow(self):
        with FakeSlack() as fake:
            fake.client().files_upload_v2(channel="C1", file=io.BytesIO(b"# report"), filename="r.md", initial_comment="memo")
            self.assertEqual(fake.paths(), ["/api/files.getUploadURLExternal", "/upload/abc", "/api/files.completeUploadExternal"])
            get, up, done = fake.requests
            self.assertEqual(get["body"], {"filename": "r.md", "length": "8"})
            self.assertEqual(up["body"], b"# report")
            self.assertEqual(done["body"], {"files": [{"id": "F123", "title": "r.md"}], "channel_id": "C1", "initial_comment": "memo"})

    def test_api_error_raises(self):
        with FakeSlack() as fake:
            with self.assertRaises(lf.SlackApiError):
                fake.client()._api("nope.method")


# ----- ハンドラ全体（偽 S3 / 偽 Secrets Manager / 偽 Slack） ------------------------------
class FakeS3:
    def __init__(self, objects: dict[str, tuple[bytes, datetime]]):
        self.objects = objects

    def get_paginator(self, name):
        objs = self.objects

        class P:
            def paginate(self, **kw):
                yield {"Contents": [{"Key": k, "LastModified": t} for k, (_, t) in objs.items()]}
        return P()

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise _FakeClientError("NoSuchKey")
        return {"Body": io.BytesIO(self.objects[Key][0])}


class FakeSecrets:
    def __init__(self, port):
        self.port = port

    def get_secret_value(self, SecretId):
        return {"SecretString": json.dumps({"bot_token": "xoxb-test", "channel_id": "C1"})}


class FakeContext:
    invoked_function_arn = "arn:aws:lambda:ap-northeast-1:123456789012:function:aws-risk-weekly-slack"


class HandlerTests(unittest.TestCase):
    def run_handler(self, fake: FakeSlack, objects: dict, event: dict, polish: bool = False):
        orig = (lf.s3, lf.secrets, lf.SlackClient.__init__, lf.POLISH_WITH_OPENAI)
        base = f"http://127.0.0.1:{fake.port}/api/"
        init = lf.SlackClient.__init__

        def patched_init(self_, token, base_url=base, timeout=30):
            init(self_, token, base_url=base_url, timeout=timeout)
        try:
            lf.s3, lf.secrets, lf.SlackClient.__init__, lf.POLISH_WITH_OPENAI = FakeS3(objects), FakeSecrets(fake.port), patched_init, polish
            return lf.handler(event, FakeContext())
        finally:
            lf.s3, lf.secrets, lf.SlackClient.__init__, lf.POLISH_WITH_OPENAI = orig

    def fresh(self):
        return datetime.now(timezone.utc) - timedelta(hours=1)

    def test_success_posts_summary_then_attaches_original_report(self):
        objects = {"checkRiskReport_20260921_090000.md": (fixture("report_sample.md"), self.fresh())}
        with FakeSlack() as fake:
            out = self.run_handler(fake, objects, {"outcome": "success", "detail": {"build-status": "SUCCEEDED"}})
            self.assertEqual(out, {"ok": True, "file": "checkRiskReport_20260921_090000.md"})
            self.assertEqual(fake.paths(), ["/api/chat.postMessage", "/api/files.getUploadURLExternal", "/upload/abc", "/api/files.completeUploadExternal"])
            text = fake.requests[0]["body"]["text"]
            self.assertIn("🚨 クリティカルリスクあり", text)
            self.assertIn("- High:      17", text)
            self.assertEqual(fake.requests[1]["body"]["filename"], "checkRiskReport_20260921_090000.md")

    def test_polished_report_is_attached_and_top5_shown_when_enabled(self):
        t = self.fresh()
        objects = {
            "checkRiskReport_20260921_090000.md": (fixture("report_sample.md"), t),
            "checkRiskReport_20260921_090000_polished.md": (fixture("report_polished_new_heading.md"), t),
        }
        with FakeSlack() as fake:
            out = self.run_handler(fake, objects, {"outcome": "success", "detail": {}}, polish=True)
            self.assertEqual(out["file"], "checkRiskReport_20260921_090000_polished.md")
            self.assertIn("### 🔴 今すぐ対応（Top5）", fake.requests[0]["body"]["text"])

    def test_failure_event_posts_one_message_and_no_attachment(self):
        objects = {"checkRiskReport_20260914_090000.md": (fixture("report_sample.md"), self.fresh())}
        event = {"outcome": "failure", "detail": {"build-status": "FAILED", "build-id": "arn:aws:codebuild:ap-northeast-1:1:build/aws-risk-weekly:u-1",
                                                  "additional-information": {"logs": {"deep-link": "https://logs.example/x"}}}}
        with FakeSlack() as fake:
            out = self.run_handler(fake, objects, event)
            self.assertEqual(out, {"ok": True, "outcome": "failure"})
            self.assertEqual(fake.paths(), ["/api/chat.postMessage"])
            text = fake.requests[0]["body"]["text"]
            self.assertIn("実行できませんでした（CodeBuild: FAILED）", text)
            self.assertIn("https://logs.example/x", text)
            self.assertNotIn("Critical", text)

    def test_stale_report_is_not_posted_as_this_week(self):
        old = datetime.now(timezone.utc) - timedelta(days=7)
        objects = {"checkRiskReport_20260914_090000.md": (fixture("report_sample.md"), old)}
        with FakeSlack() as fake:
            out = self.run_handler(fake, objects, {"outcome": "success", "detail": {"build-status": "SUCCEEDED"}})
            self.assertEqual(out["outcome"], "missing-report")
            self.assertEqual(fake.paths(), ["/api/chat.postMessage"])
            self.assertIn("今週のレポートが見つかりません", fake.requests[0]["body"]["text"])

    def test_no_report_at_all(self):
        with FakeSlack() as fake:
            out = self.run_handler(fake, {}, {})
            self.assertEqual(out["outcome"], "missing-report")
            self.assertIn("レポートなし", fake.requests[0]["body"]["text"])

    def test_upload_failure_adds_note_instead_of_raising(self):
        objects = {"checkRiskReport_20260921_090000.md": (fixture("report_empty.md"), self.fresh())}
        with FakeSlack(fail_upload=True) as fake:
            out = self.run_handler(fake, objects, {"outcome": "success", "detail": {}})
            self.assertEqual(out["error"], "upload-failed")
            self.assertEqual(fake.paths(), ["/api/chat.postMessage", "/api/files.getUploadURLExternal", "/upload/abc", "/api/chat.postMessage"])
            self.assertIn("添付に失敗しました", fake.requests[-1]["body"]["text"])
            self.assertIn("🟢", fake.requests[0]["body"]["text"])


if __name__ == "__main__":
    unittest.main()
