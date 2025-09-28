# lambda_function.py
import os, io, boto3, re, json
from datetime import date, datetime
from zoneinfo import ZoneInfo
from slack_sdk import WebClient
from botocore.exceptions import ClientError

# ----- Env (既存のまま) ------------------------------------------------------------
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX","risk/weekly/out/")
SLACK_SECRET_NAME = os.environ["SLACK_SECRET_NAME"]
POLISH_WITH_OPENAI = os.environ.get("POLISH_WITH_OPENAI", "false").lower() == "true"

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

def pick_greeting(arr: list[str]) -> str:
    '''JSTの1/1からの通算日を使って週ごとに1つ前進。24超えたら24を引く（=0..23でローテ）'''
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    yday = today.timetuple().tm_yday       # 1..366
    quotient = (yday - 1) // 7             # ←「割れた数」
    n = len(arr)                            # 24
    while quotient >= n:                    # 24を引き続けて範囲内へ（= quotient % n）
        quotient -= n
    idx = quotient                          # 0..23
    return arr[idx]

# ----- Slack / S3 helpers -----------------------------------------------------------
def _slack():
    sec = secrets.get_secret_value(SecretId=SLACK_SECRET_NAME)["SecretString"]
    data = json.loads(sec)
    return WebClient(token=data["bot_token"]), data["channel_id"]

def _latest_report_base_key():
    '''最新（LastModified最大）の .md/_polished.md を見てベースキーを返す'''
    p = s3.get_paginator('list_objects_v2')
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
    if not latest_base:
        raise RuntimeError("No report files found under " + S3_PREFIX)
    return latest_base

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
    # 正規表現: 「### ...今すぐ対応 Top5...」で始まる行から、次の「## 」で始まる行、またはファイルの終わりまでをマッチ
    m = re.search(r"(^###\s.*今すぐ対応 Top5.*$[\s\S]*?)(?=^##\s|\Z)", text, re.MULTILINE)
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

# ----- Lambda handler ---------------------------------------------------------------
def handler(event, context):
    base_key = _latest_report_base_key()
    original_key = base_key + ".md"
    polished_key = base_key + "_polished.md"

    # 元レポートを取得（件数は常にオリジナルから取る）
    original_obj = s3.get_object(Bucket=S3_BUCKET, Key=original_key)
    original_md_bytes = original_obj["Body"].read()
    original_summary_lines = _extract_original_summary(original_md_bytes)

    # 添付は既定でオリジナル、POLISH_WITH_OPENAI=true なら_polished.mdがあれば差し替え
    md_bytes = original_md_bytes
    file_to_attach_key = original_key
    top5_block = ""  # 本文に出すブロック（存在すれば）
    if POLISH_WITH_OPENAI:
        try:
            polished_obj = s3.get_object(Bucket=S3_BUCKET, Key=polished_key)
            polished_md_bytes = polished_obj["Body"].read()
            # 添付は_polished.mdに差し替え
            md_bytes = polished_md_bytes
            file_to_attach_key = polished_key
            # Top5ブロックはまず_polishedから
            top5_block = _extract_top5_block(polished_md_bytes)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "NoSuchKey":
                raise
            print(f"Warning: Polished file {polished_key} not found. Proceeding with original.")
    # polishedが無い/抽出できない場合はオリジナルからも試す
    if not top5_block:
        top5_block = _extract_top5_block(original_md_bytes)

    # 本文構築
    counts = _parse_counts(original_summary_lines)
    risk_msg = _risk_banner(counts)
    summary_block = _format_counts_block(counts) if original_summary_lines else "(レポートからサマリーを抽出できませんでした)"
    account_id = context.invoked_function_arn.split(':')[4] if context else "unknown"
    today_str = date.today().isoformat()
    title = f":white_check_mark: AWS Risk Weekly ({account_id}) — {today_str}"
    greeting = pick_greeting(GREETINGS)

    body = (
        f"{title}\n\n"
        f"{greeting}\n\n"
        f"{risk_msg}\n\n"
        f"{summary_block}"
    )
    if top5_block:
        body += "\n\n" + top5_block

    # Slack送信（空添付対策：BytesIOで毎回新規に詰める）
    slack, channel = _slack()
    slack.chat_postMessage(channel=channel, text=body, icon_emoji=":white_check_mark:")
    slack.files_upload_v2(
        channel=channel,
        file=io.BytesIO(md_bytes),
        filename=file_to_attach_key.split("/")[-1],
        initial_comment=":memo: レポート（Markdown）を添付します。",
    )
    return {"ok": True, "file": file_to_attach_key}