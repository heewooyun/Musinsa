#!/usr/bin/env python3
"""Send the rendered 무신사 장외일보 by email. Standard library only.

Backends (picked automatically from environment variables, or force one with --backend):
  resend : RESEND_API_KEY
           HTTPS API, so it also works where SMTP ports are blocked (e.g. a Claude Code cloud
           environment with api.resend.com allowed). Without a verified domain Resend only
           delivers to the address that owns the Resend account; that is enough for a personal
           newsletter. Sender defaults to onboarding@resend.dev.
  smtp   : GMAIL_ADDRESS + GMAIL_APP_PASSWORD  (smtp.gmail.com:465, needs a Google "app password")
           or SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD for any other SMTP server.

Recipient: --to, or NEWSLETTER_TO. Keep the address in a secret/env var, not in the repo.

Usage:
  python3 send_email.py --html out/newsletter.html --text out/newsletter.txt \
      --subject-file out/subject.txt [--to you@example.com] [--wait-until 07:00] [--dry-run]

Exit codes: 0 sent (or dry run OK), 2 missing input/credentials, 3 sending failed.
The script never prints secrets.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.request
from email.header import Header
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))
DISPLAY_NAME = "무신사 장외일보"
MAX_WAIT_MINUTES = 90


def log(**kw) -> None:
    print(json.dumps(kw, ensure_ascii=False))


def wait_until(hhmm: str) -> None:
    """Sleep until HH:MM KST today if that moment is ahead of us and within MAX_WAIT_MINUTES."""
    h, m = (int(x) for x in hhmm.split(":"))
    now = dt.datetime.now(KST)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    delta = (target - now).total_seconds()
    if delta <= 0:
        return
    if delta > MAX_WAIT_MINUTES * 60:
        log(event="wait_skipped", reason=f"{hhmm} KST까지 {int(delta // 60)}분 남아 대기하지 않고 바로 보냅니다.")
        return
    log(event="waiting", until=f"{hhmm} KST", seconds=int(delta))
    time.sleep(delta)


def pick_backend(forced: str | None) -> str | None:
    if forced:
        return forced
    if os.environ.get("RESEND_API_KEY"):
        return "resend"
    if (os.environ.get("GMAIL_ADDRESS") and os.environ.get("GMAIL_APP_PASSWORD")) or (
        os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD")
    ):
        return "smtp"
    return None


def send_resend(to: str, subject: str, html: str, text: str) -> str:
    sender = os.environ.get("NEWSLETTER_FROM") or f"{DISPLAY_NAME} <onboarding@resend.dev>"
    body = json.dumps({"from": sender, "to": [to], "subject": subject, "html": html, "text": text}).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": "musinsa-ipo-daily-briefing/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}").get("id", "")


def send_smtp(to: str, subject: str, html: str, text: str) -> str:
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or 465)
    user = os.environ.get("SMTP_USER") or os.environ["GMAIL_ADDRESS"]
    password = os.environ.get("SMTP_PASSWORD") or os.environ["GMAIL_APP_PASSWORD"]
    sender = os.environ.get("NEWSLETTER_FROM") or formataddr((str(Header(DISPLAY_NAME, "utf-8")), user))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1])
    msg.set_content(text, charset="utf-8")
    msg.add_alternative(html, subtype="html", charset="utf-8")

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=context)
            s.login(user, password)
            s.send_message(msg)
    return msg["Message-ID"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", required=True)
    ap.add_argument("--text", help="plain-text alternative (recommended)")
    ap.add_argument("--subject")
    ap.add_argument("--subject-file")
    ap.add_argument("--to", default=os.environ.get("NEWSLETTER_TO"))
    ap.add_argument("--backend", choices=["resend", "smtp"])
    ap.add_argument("--wait-until", metavar="HH:MM", help="hold the send until this KST time (max 90 min)")
    ap.add_argument("--dry-run", action="store_true", help="check everything but do not send")
    args = ap.parse_args()

    try:
        html = Path(args.html).read_text(encoding="utf-8")
        text = Path(args.text).read_text(encoding="utf-8") if args.text else "HTML 메일입니다. HTML을 지원하는 메일 앱에서 열어 주세요."
        subject = args.subject or (Path(args.subject_file).read_text(encoding="utf-8").strip() if args.subject_file else "")
    except FileNotFoundError as e:
        log(sent=False, error=f"입력 파일 없음: {e.filename}")
        return 2
    if not subject:
        log(sent=False, error="--subject 또는 --subject-file이 필요합니다.")
        return 2
    if not args.to:
        log(sent=False, error="수신자가 없습니다: --to 또는 NEWSLETTER_TO 환경변수를 설정하세요.")
        return 2

    backend = pick_backend(args.backend)
    if backend is None:
        log(sent=False, error="메일 자격증명이 없습니다: RESEND_API_KEY 또는 GMAIL_ADDRESS+GMAIL_APP_PASSWORD를 설정하세요.")
        return 2
    if args.dry_run:
        log(sent=False, dry_run=True, backend=backend, to=args.to, subject=subject, html_bytes=len(html.encode()))
        return 0
    if args.wait_until:
        wait_until(args.wait_until)

    sender_fn = send_resend if backend == "resend" else send_smtp
    last_error = ""
    for attempt in range(1, 4):
        try:
            msg_id = sender_fn(args.to, subject, html, text)
            log(sent=True, backend=backend, to=args.to, subject=subject, id=msg_id,
                at=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"))
            return 0
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            last_error = f"HTTP {e.code}: {detail}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except smtplib.SMTPAuthenticationError:
            last_error = "SMTP 로그인 실패 — Gmail '앱 비밀번호'(16자리)인지, 2단계 인증이 켜져 있는지 확인하세요."
            break
        except (OSError, smtplib.SMTPException, urllib.error.URLError) as e:
            last_error = f"{type(e).__name__}: {e}"
        time.sleep(2 ** attempt)
    log(sent=False, backend=backend, error=last_error)
    return 3


if __name__ == "__main__":
    sys.exit(main())
