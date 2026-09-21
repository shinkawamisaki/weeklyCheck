# lambda_function.py
import os, io, boto3, re, json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from slack_sdk import WebClient
from botocore.exceptions import ClientError

# ----- Env ---------------------------------------------------------------------------
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX", "")
SLACK_SECRET_NAME = os.environ["SLACK_SECRET_NAME"]
POLISH_WITH_OPENAI = os.environ.get("POLISH_WITH_OPENAI", "false").lower() in ("1", "true")
# 成功イベントを受けたとき、これより古いレポートしか無ければ「今週の結果ではない」と判断して通知する
MAX_REPORT_AGE_HOURS = int(os.environ.get("MAX_REPORT_AGE_HOURS", "24"))
JST = ZoneInfo("Asia/Tokyo")

# ----- AWS Clients -----------------------------------------------------------------
s3 = boto3.client("s3", region_name=REGION)
secrets = boto3.client("secretsmanager", region_name=REGION)

# ----- 挨拶（24本・JST週ローテ） ---------------------------------------------------
GREETINGS = [
    "雲（Cloud）のなかから、今週もお届けしています。",
    "おはようございます。AWSです。今日もよろしくお願いします。",
    "そっとリマインド。週のはじまりです。",
    "AWSです。今週のセキュリティ点検をお届けしますね。",
    "月曜の朝、ゆっくりスイッチ入れていきましょう。",
    "おはようございます！AWS見守りボットです。",
    "肩を大きく後ろにまわして。ふう、まずは自分のペースで。おはよう、AWSです。",
    "AWSです！おはようございます！",
    "AWSからちいさなエールを送ります。",
    "いつも通り、安全に。そしてぼちぼち行きましょう。AWSです",
    "あなたと一緒に、ちいさなはじまり。おはようございます、AWSです。",
    "おつかれさまです！週次のAWSチェックです",
    "まずは深呼吸ひとつ。おはようございます、AWSです。",
    "みなさんの一週間があかるくありますように。",
    "そっと、ただいまの空模様をお届けします。",
    "AWS週次レポートです！いつもありがとう。",
    "AWSです、朝ごはん食べましたか？",
    "おはようございます、AWSです。少しずつ、動き出しましょう。",
    "今日は、どんな小さなことから始めましょうか。",
    "AWSです。安全確認、完了いたしました！",
    "おはよう。まずは軽くリラックス。目を閉じて、10数えて。AWS今週のレポートです",
    "AWSです。コーヒー淹れたら、始めましょうか。",
    "小さくスタート。それでいい日になりますように。AWSです。",
    "AWSです。今週もよろしくお願いします！",
]

GREETING_EPOCH = date(2025, 9, 29)  # 月曜日。ここから数えた週数で 24 本をローテーションする

def pick_greeting(arr: list[str], today: date | None = None) -> str:
    """固定の月曜日 (GREETING_EPOCH) からの経過週数で 1 つずつ進める。
    年間通算日を使うと年末年始で同じ挨拶が続くため、暦年に依存しない基準日を使う。"""
    today = today or datetime.now(JST).date()
    weeks = (today - GREETING_EPOCH).days // 7
    return arr[weeks % len(arr)]

# ----- Slack / S3 helpers -----------------------------------------------------------
def _slack():
    sec = secrets.get_secret_value(SecretId=SLACK_SECRET_NAME)["SecretString"]
    data = json.loads(sec)
    return WebClient(token=data["bot_token"]), data["channel_id"]

def _latest_report():
    """最新（LastModified 最大）のレポートのベースキーと更新時刻を返す。無ければ (None, None)。"""
    p = s3.get_paginator("list_objects_v2")
    latest_base, latest_time = None, None
    for pg in p.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX):
        for o in pg.get("Contents", []):
            k = o["Key"]
            if not k.endswith(".md"):
                continue
            base = k.replace("_polished.md", "").replace(".md", "")
            t = o.get("LastModified")
            if latest_time is None or (t and t > latest_time):
                latest_base, latest_time = base, t
    return latest_base, latest_time

# ----- Report parsers ---------------------------------------------------------------
def _extract_original_summary(md_bytes: bytes) -> list[str]:
    text = md_bytes.decode("utf-8", errors="ignore")
    in_summary, out = False, []
    for line in text.splitlines():
        if line.strip() == "## サマリー":
            in_summary = True
            continue
        if in_summary:
            if not line.strip() and out:
                break
            if line.strip():
                out.append(line)
    return out

def _extract_top5_block(md_bytes: bytes) -> str:
    """###...今すぐ対応... セクション全体（見出し含む）を抽出。なければ空文字列"""
    text = md_bytes.decode("utf-8", errors="ignore")
    # 「### … 今すぐ対応 … Top5 …」の見出し行から、次の「# 」「## 」見出しまたはファイル末尾までを抽出する。
    # checkRisk の見出しは「### ■ 今すぐ対応 Top5 ■」（〜e396515）と「### 🔴 今すぐ対応（Top5）」（27c9a9c〜）の
    # 2 種類があるため、「今すぐ対応」と「Top5」が同じ行にあれば一致させる。
    m = re.search(r"(^###\s[^\n]*今すぐ対応[^\n]*Top5[^\n]*$[\s\S]*?)(?=^#{1,2}\s|\Z)", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""

def _parse_counts(summary_lines: list[str]) -> dict:
    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for ln in summary_lines:
        m = re.search(r"(Critical|High|Medium|Low)\s*:\s*(\d+)", ln)
        if m:
            counts[m.group(1)] = int(m.group(2))
    return counts

def _format_counts_block(counts: dict) -> str:
    return "\n".join([
        f"- Critical:  {counts['Critical']}",
        f"- High:      {counts['High']}",
        f"- Medium:   {counts['Medium']}",
        f"- Low:      {counts['Low']}",
    ])

def _risk_banner(counts: dict) -> str:
    if counts["Critical"] > 0:
        return "*🚨 クリティカルリスクあり。対応をお願いします。*"
    if counts["High"] > 0:
        return "*⚠️ ハイリスク項目あり。対応を推奨します。*"
    return "*🟢 重大なリスクはありませんでした*"

# ----- Message builders（純粋関数。テストしやすいように I/O を含めない） -------------
def _title(account_id: str, today: date) -> str:
    # タイトルの絵文字は固定。状態は本文の判定行だけで伝える（月曜の朝に 🚨 が並ばないように）
    return f":white_check_mark: AWS Risk Weekly ({account_id}) — {today.isoformat()}"

def build_success_message(account_id: str, today: date, summary_lines: list[str], top5_block: str, greeting: str) -> str:
    counts = _parse_counts(summary_lines)
    summary_block = _format_counts_block(counts) if summary_lines else "(レポートからサマリーを抽出できませんでした)"
    body = (
        f"{_title(account_id, today)}\n\n"
        f"{greeting}\n\n"
        f"{_risk_banner(counts)}\n\n"
        f"{summary_block}"
    )
    if top5_block:
        body += "\n\n" + top5_block
    return body

def build_failure_message(account_id: str, today: date, greeting: str, reason: str,
                          build_id: str = "", log_url: str = "") -> str:
    """実行失敗・レポート欠落のとき。リスクの有無は「不明」であることをはっきり書く。"""
    lines = [
        _title(account_id, today),
        "",
        greeting,
        "",
        f"*⚠️ 今週のチェックは実行できませんでした（{reason}）。*",
        "リスクの有無はまだ判定できていません。ログを確認してください。",
    ]
    if build_id:
        lines.append(f"- ビルド: `{build_id.split('/')[-1]}`")
    if log_url:
        lines.append(f"- ログ: {log_url}")
    return "\n".join(lines)

def _outcome_of(event: dict) -> tuple[str, dict]:
    """EventBridge ルールが付けた outcome を読む。無ければ CodeBuild の build-status から推定する
    （手動テストで {} を渡したときは success 扱い＝最新レポートを通知）。"""
    detail = event.get("detail") or {}
    outcome = event.get("outcome")
    if outcome not in ("success", "failure"):
        status = detail.get("build-status")
        outcome = "success" if status in (None, "SUCCEEDED") else "failure"
    return outcome, detail

# ----- Lambda handler ---------------------------------------------------------------
def handler(event, context):
    outcome, detail = _outcome_of(event or {})
    account_id = context.invoked_function_arn.split(":")[4] if context else "unknown"
    today = datetime.now(JST).date()
    greeting = pick_greeting(GREETINGS, today)
    slack, channel = _slack()

    build_id = detail.get("build-id", "")
    log_url = ((detail.get("additional-information") or {}).get("logs") or {}).get("deep-link", "")

    # 1) 実行失敗（FAILED / FAULT / STOPPED / TIMED_OUT）: 何も来ない状態を作らない
    if outcome != "success":
        reason = f"CodeBuild: {detail.get('build-status', 'unknown')}"
        slack.chat_postMessage(channel=channel, text=build_failure_message(account_id, today, greeting, reason, build_id, log_url),
                               icon_emoji=":white_check_mark:")
        return {"ok": True, "outcome": "failure"}

    # 2) 成功イベントだが新しいレポートが無い: 先週のレポートを今週の結果として流さない
    base_key, modified = _latest_report()
    now = datetime.now(timezone.utc)
    if base_key is None or modified is None or (now - modified) > timedelta(hours=MAX_REPORT_AGE_HOURS):
        seen = f"最新は {modified.astimezone(JST):%Y-%m-%d %H:%M}" if modified else "レポートなし"
        reason = f"S3 に今週のレポートが見つかりません。{seen}"
        slack.chat_postMessage(channel=channel, text=build_failure_message(account_id, today, greeting, reason, build_id, log_url),
                               icon_emoji=":white_check_mark:")
        return {"ok": True, "outcome": "missing-report"}

    original_key = base_key + ".md"
    polished_key = base_key + "_polished.md"

    # 元レポートを取得（件数は常にオリジナルから取る）
    original_md_bytes = s3.get_object(Bucket=S3_BUCKET, Key=original_key)["Body"].read()
    original_summary_lines = _extract_original_summary(original_md_bytes)

    # 添付は既定でオリジナル。POLISH_WITH_OPENAI が有効で _polished.md があればそちらに差し替え
    md_bytes = original_md_bytes
    file_to_attach_key = original_key
    top5_block = ""
    if POLISH_WITH_OPENAI:
        try:
            polished_md_bytes = s3.get_object(Bucket=S3_BUCKET, Key=polished_key)["Body"].read()
            md_bytes = polished_md_bytes
            file_to_attach_key = polished_key
            top5_block = _extract_top5_block(polished_md_bytes)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "NoSuchKey":
                raise
            print(f"Warning: Polished file {polished_key} not found. Proceeding with original.")
    if not top5_block:
        top5_block = _extract_top5_block(original_md_bytes)

    body = build_success_message(account_id, today, original_summary_lines, top5_block, greeting)

    # 3) 本文 → 添付の順に送る。添付だけ失敗したときは例外で終わらせない
    #    （EventBridge の再試行で本文が二重投稿されるのを防ぐ。失敗はログと短い追記で伝える）
    slack.chat_postMessage(channel=channel, text=body, icon_emoji=":white_check_mark:")
    filename = file_to_attach_key.split("/")[-1]
    try:
        slack.files_upload_v2(
            channel=channel,
            file=io.BytesIO(md_bytes),
            filename=filename,
            initial_comment=":memo: レポート（Markdown）を添付します。",
        )
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: file upload failed for {file_to_attach_key}: {e!r}")
        slack.chat_postMessage(channel=channel,
                               text=f":memo: レポートの添付に失敗しました。S3 の `{file_to_attach_key}` を直接確認してください。")
        return {"ok": False, "file": file_to_attach_key, "error": "upload-failed"}
    return {"ok": True, "file": file_to_attach_key}
