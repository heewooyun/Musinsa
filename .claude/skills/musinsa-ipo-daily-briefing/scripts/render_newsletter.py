#!/usr/bin/env python3
"""Render 무신사 장외일보: briefing JSON -> email-safe HTML + plain text + subject line.

Usage:
  python3 render_newsletter.py --in out/briefing.json --out-dir out
  python3 render_newsletter.py --in out/briefing.json --check      # validate only

Writes newsletter.html, newsletter.txt and subject.txt into --out-dir and prints a JSON
report (ok, errors, warnings, opinion_chars, ...) to stdout.

Exit codes: 0 = rendered (warnings may exist), 1 = validation errors (fix briefing.json and
re-run), 2 = usage/environment problem (missing file, jinja2 not installed).

The JSON contract is documented in references/output-contract.md and
assets/briefing.example.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "assets"
TEMPLATE_NAME = "newsletter_template.html"

BRAND = "무신사 장외일보"
TAGLINE = "무신사 비상장 주주를 위한 3분 모닝 브리핑"
OPINION_MIN, OPINION_MAX = 300, 500  # 공백 포함 글자 수
WEEKDAYS = "월화수목금토일"
TIER_LABELS = {"T1": "공식", "T2": "언론·리포트", "T3": "분석", "T4": "커뮤니티·참고용"}
FACT_KINDS = {"수정", "주의", "확인"}
DEFAULT_DISCLAIMER = (
    "이 메일은 공개된 뉴스·공시·시세 자료를 바탕으로 AI가 자동 작성한 개인 참고용 리서치 요약이며, "
    "특정 증권의 매수·매도를 권유하지 않습니다. ‘예측’으로 표시된 내용은 확정된 사실이 아니고, 수치는 "
    "기준 시점에 따라 달라질 수 있습니다. 블랙·화이트·레드·블루는 분석용 가상 AI 페르소나로 무신사 및 "
    "실존 인물과 관계가 없습니다. 투자 판단과 그 결과의 책임은 본인에게 있습니다."
)

BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
URL_RE = re.compile(r"^https?://\S+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MARK_RE = re.compile(r"\x00(\d+)\x00")
SUP_STYLE = "font-size:10px;line-height:0;font-weight:800;color:#2F6BFF;vertical-align:super;"
STRONG_STYLE = "background:#FFF0A8;font-weight:800;"


def plain(text: str | None) -> str:
    return BOLD_RE.sub(r"\1", text or "")


def char_count(text: str | None) -> int:
    """Characters including spaces; runs of whitespace/newlines count as one space."""
    return len(re.sub(r"\s+", " ", plain(text)).strip())


class Annotator:
    """Adds glossary footnote numbers to the first occurrence of each term, in reading order."""

    def __init__(self, terms: list[str]):
        self.terms = terms
        self.by_length = sorted(range(len(terms)), key=lambda i: -len(terms[i]))
        self.first_seen: list[int] = []
        self.numbers: dict[int, int] = {}

    def mark(self, text: str | None) -> str:
        text = text or ""
        claimed: list[tuple[int, int]] = []
        hits: list[tuple[int, int]] = []  # (end_position, term_index)
        for idx in self.by_length:
            term = self.terms[idx]
            if not term or idx in self.first_seen or any(h[1] == idx for h in hits):
                continue
            start = text.find(term)
            while start != -1:
                end = start + len(term)
                if all(end <= s or start >= e for s, e in claimed):
                    claimed.append((start, end))
                    hits.append((end, idx))
                    break
                start = text.find(term, start + 1)
        for end, idx in sorted(hits):
            self.first_seen.append(idx)
        for end, idx in sorted(hits, reverse=True):
            text = f"{text[:end]}\x00{idx}\x00{text[end:]}"
        return text

    def assign_numbers(self) -> None:
        order = self.first_seen + [i for i in range(len(self.terms)) if i not in self.first_seen]
        self.numbers = {idx: n for n, idx in enumerate(order, start=1)}

    def to_html(self, marked: str):
        from markupsafe import Markup

        out = html.escape(marked, quote=True)
        out = MARK_RE.sub(lambda m: f'<sup style="{SUP_STYLE}">{self.numbers[int(m.group(1))]}</sup>', out)
        out = BOLD_RE.sub(lambda m: f'<strong style="{STRONG_STYLE}">{m.group(1)}</strong>', out)
        out = out.replace("\r\n", "\n").replace("\n\n", "<br><br>").replace("\n", "<br>")
        return Markup(out)

    def to_text(self, marked: str) -> str:
        return plain(MARK_RE.sub(lambda m: f"[{self.numbers[int(m.group(1))]}]", marked))


def validate(d: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    date = d.get("date", "")
    issue_date = None
    if not DATE_RE.match(str(date)):
        errors.append("date: 'YYYY-MM-DD' 형식의 발행일(KST)이 필요합니다.")
    else:
        try:
            issue_date = dt.date.fromisoformat(date)
        except ValueError:
            errors.append(f"date: 존재하지 않는 날짜입니다 ({date}).")

    headline = (d.get("headline") or "").strip()
    if not headline:
        errors.append("headline: '오늘의 한 줄'이 비어 있습니다.")
    elif len(headline) > 45:
        warnings.append(f"headline: {len(headline)}자 — 45자 이하가 모바일 제목 줄에 잘 맞습니다.")
    if len(d.get("preheader") or "") > 90:
        warnings.append("preheader: 90자 이하를 권장합니다(받은편지함 미리보기).")

    opinion = d.get("opinion") or {}
    n = char_count(opinion.get("body"))
    if not (OPINION_MIN <= n <= OPINION_MAX):
        errors.append(f"opinion.body: {n}자 — 공백 포함 {OPINION_MIN}~{OPINION_MAX}자로 맞춰 주세요.")

    arts = d.get("articles") or []
    if len(arts) == 5:
        pass
    elif 1 <= len(arts) < 5 and (d.get("shortfall_reason") or "").strip():
        warnings.append(f"articles: {len(arts)}개 — shortfall_reason과 함께 발행합니다.")
    else:
        errors.append(
            f"articles: {len(arts)}개 — 정확히 5개가 필요합니다(최근 7일 자료까지 찾아도 기준 통과 자료가 "
            "5개 미만이면 shortfall_reason을 적으세요. 무관한 자료로 채우지 마세요)."
        )
    seen_urls: set[str] = set()
    for i, a in enumerate(arts, start=1):
        tag = f"articles[{i}]"
        for key in ("title", "source", "published", "url", "summary"):
            if not str(a.get(key) or "").strip():
                errors.append(f"{tag}.{key}: 비어 있습니다.")
        url = str(a.get("url") or "")
        if url and not URL_RE.match(url):
            errors.append(f"{tag}.url: http(s) 주소가 아닙니다 ({url}).")
        if url in seen_urls:
            errors.append(f"{tag}.url: 중복된 기사입니다 ({url}).")
        seen_urls.add(url)
        pub = str(a.get("published") or "")
        if pub and not DATE_RE.match(pub):
            errors.append(f"{tag}.published: 'YYYY-MM-DD' 형식이어야 합니다 ({pub}).")
        elif pub and issue_date:
            try:
                age = (issue_date - dt.date.fromisoformat(pub)).days
                if age < 0:
                    errors.append(f"{tag}.published: 발행일({date})보다 미래 날짜입니다 ({pub}).")
                elif age > 7:
                    warnings.append(f"{tag}: {age}일 지난 자료입니다 — '지난 자료'임을 요약에 밝혔는지 확인하세요.")
            except ValueError:
                errors.append(f"{tag}.published: 존재하지 않는 날짜입니다 ({pub}).")
        if a.get("tier") and a["tier"] not in TIER_LABELS:
            warnings.append(f"{tag}.tier: T1~T4 중 하나를 쓰세요 ({a['tier']}).")
        if char_count(a.get("summary")) > 180:
            warnings.append(f"{tag}.summary: 180자 이하로 줄이면 더 읽기 좋습니다.")
        if char_count(a.get("why")) > 120:
            warnings.append(f"{tag}.why: 120자 이하를 권장합니다.")

    for i, p in enumerate(d.get("predictions") or [], start=1):
        for key in ("label", "value", "basis"):
            if not str(p.get(key) or "").strip():
                errors.append(f"predictions[{i}].{key}: 비어 있습니다(예측에는 반드시 근거가 붙어야 합니다).")

    for i, s in enumerate(d.get("snapshot") or [], start=1):
        if not s.get("label") or not s.get("value"):
            errors.append(f"snapshot[{i}]: label과 value가 필요합니다.")
        if not s.get("source_url") and not s.get("is_estimate"):
            warnings.append(f"snapshot[{i}] '{s.get('label')}': 출처 URL이 없고 예측 표시도 없습니다.")
        if s.get("source_url") and not URL_RE.match(str(s["source_url"])):
            errors.append(f"snapshot[{i}].source_url: http(s) 주소가 아닙니다.")

    glossary = d.get("glossary") or []
    if not glossary:
        errors.append("glossary: 비금융인을 위한 용어 주석이 최소 1개 필요합니다.")
    elif len(glossary) > 10:
        warnings.append(f"glossary: {len(glossary)}개 — 10개 이하로 추리면 더 읽기 좋습니다.")
    for i, g in enumerate(glossary, start=1):
        if not g.get("term") or not g.get("definition"):
            errors.append(f"glossary[{i}]: term과 definition이 필요합니다.")

    for i, f in enumerate(d.get("fact_check") or [], start=1):
        if f.get("kind") not in FACT_KINDS:
            warnings.append(f"fact_check[{i}].kind: 수정/주의/확인 중 하나를 쓰세요 — '주의'로 표시합니다.")
    if len(d.get("qa") or []) > 2:
        warnings.append("qa: 2개 이하를 권장합니다.")

    sc = d.get("scorecard")
    if not isinstance(sc, dict):
        errors.append("scorecard: 4인 채점 결과(black/white/red/blue/rounds)가 필요합니다.")
    else:
        low = []
        for who in ("black", "white", "red", "blue"):
            v = sc.get(who)
            if not isinstance(v, (int, float)) or not 0 <= v <= 10:
                errors.append(f"scorecard.{who}: 0~10 사이 숫자가 필요합니다.")
            elif v < 9:
                low.append(who)
        if low and not (d.get("quality_note") or "").strip():
            errors.append(f"scorecard: {', '.join(low)} 점수가 9점 미만입니다 — 더 고도화하거나 quality_note에 사유를 적으세요.")
    return errors, warnings


def build(d: dict):
    terms = [str(g.get("term") or "") for g in d.get("glossary") or []]
    ann = Annotator(terms)

    # Reading order decides footnote numbering.
    op_marked = ann.mark((d.get("opinion") or {}).get("body"))
    preds = [dict(p, _m=ann.mark(p.get("basis"))) for p in d.get("predictions") or []]
    qa = [dict(q, _m=ann.mark(q.get("a"))) for q in d.get("qa") or []]
    arts = [dict(a, _ms=ann.mark(a.get("summary")), _mw=ann.mark(a.get("why"))) for a in d.get("articles") or []]
    facts = [dict(f, _m=ann.mark(f.get("text"))) for f in d.get("fact_check") or []]
    ann.assign_numbers()
    unused = [terms[i] for i in range(len(terms)) if i not in ann.first_seen]

    issue = dt.date.fromisoformat(d["date"])
    wd = WEEKDAYS[issue.weekday()]
    date_label = f"{issue.year}년 {issue.month}월 {issue.day}일 {wd}요일"
    subject = f"[{BRAND}] {issue.month}/{issue.day}({wd}) {d['headline'].strip()}"

    def short_date(s: str) -> str:
        try:
            x = dt.date.fromisoformat(s)
            return f"{x.month}/{x.day}"
        except ValueError:
            return s

    glossary_sorted = sorted(
        ({"n": ann.numbers[i], "term": terms[i], "definition": g.get("definition", "")}
         for i, g in enumerate(d.get("glossary") or [])),
        key=lambda g: g["n"],
    )
    sc = d.get("scorecard") or {}
    ctx = {
        "subject": subject,
        "brand_name": BRAND,
        "tagline": d.get("tagline") or TAGLINE,
        "date_label": date_label,
        "preheader": d.get("preheader") or plain(d["headline"]),
        "headline": plain(d["headline"]),
        "greeting": plain(d.get("greeting")),
        "snapshot": [
            {**s, "change_dir": s.get("change_dir") or _guess_dir(s.get("change"))}
            for s in d.get("snapshot") or []
        ],
        "opinion": {"title": (d.get("opinion") or {}).get("title") or "오늘의 전문가 의견",
                    "body_html": ann.to_html(op_marked)},
        "predictions": [{**p, "basis_html": ann.to_html(p["_m"])} for p in preds],
        "qa": [{"q": plain(q.get("q")), "a_html": ann.to_html(q["_m"])} for q in qa],
        "articles": [
            {**a, "published_label": short_date(str(a.get("published", ""))),
             "tier_label": TIER_LABELS.get(a.get("tier", ""), ""),
             "title": plain(a.get("title")),
             "summary_html": ann.to_html(a["_ms"]), "why_html": ann.to_html(a["_mw"]) if a.get("why") else ""}
            for a in arts
        ],
        "shortfall_reason": d.get("shortfall_reason"),
        "fact_check": [{"kind": f.get("kind") if f.get("kind") in FACT_KINDS else "주의",
                        "text_html": ann.to_html(f["_m"])} for f in facts],
        "glossary": glossary_sorted,
        "scorecard": ({k: _fmt_score(sc.get(k)) for k in ("black", "white", "red", "blue")}
                      | {"rounds": sc.get("rounds", 1)}) if sc else None,
        "quality_note": d.get("quality_note"),
        "method_note": d.get("method_note"),
        "disclaimer": d.get("disclaimer") or DEFAULT_DISCLAIMER,
    }

    # Plain-text alternative (multipart/alternative part of the email, also handy for logs).
    t: list[str] = [f"{BRAND} | {date_label}", "", ctx["headline"], ""]
    if ctx["greeting"]:
        t += [ctx["greeting"], ""]
    if ctx["snapshot"]:
        t.append("■ 숫자로 보는 오늘")
        for s in ctx["snapshot"]:
            line = f"· {s['label']}: {s['value']}"
            if s.get("change"):
                line += f" ({s['change']})"
            if s.get("is_estimate"):
                line += " [예측]"
            if s.get("note"):
                line += f" — {s['note']}"
            t.append(line)
        t.append("")
    t += [f"■ {ctx['opinion']['title']}", ann.to_text(op_marked), ""]
    if preds:
        t.append("■ 블랙의 예측 노트 (예측 · 확정 아님)")
        for p in preds:
            conf = f" / 신뢰도 {p['confidence']}" if p.get("confidence") else ""
            t.append(f"· {p['label']}: {p['value']}{conf} — 근거: {ann.to_text(p['_m'])}")
        t.append("")
    if qa:
        t.append("■ 화이트가 묻고, 블랙이 답했어요")
        for q in qa:
            t += [f"Q. {plain(q.get('q'))}", f"A. {ann.to_text(q['_m'])}"]
        t.append("")
    t.append(f"■ 오늘 꼭 볼 자료 TOP {len(arts)}")
    if d.get("shortfall_reason"):
        t.append(f"({d['shortfall_reason']})")
    for i, a in enumerate(arts, start=1):
        cat = f"[{a['category']}] " if a.get("category") else ""
        t.append(f"{i}. {cat}{plain(a.get('title'))} — {a.get('source')}, {short_date(str(a.get('published')))}")
        t.append(f"   {ann.to_text(a['_ms'])}")
        if a.get("why"):
            t.append(f"   왜 중요해? {ann.to_text(a['_mw'])}")
        t.append(f"   {a.get('url')}")
    t.append("")
    if facts:
        t.append("■ 레드의 팩트체크")
        for f in facts:
            t.append(f"· [{f.get('kind', '주의')}] {ann.to_text(f['_m'])}")
        t.append("")
    if glossary_sorted:
        t.append("■ 오늘의 용어 풀이")
        for g in glossary_sorted:
            t.append(f"[{g['n']}] {g['term']} — {g['definition']}")
        t.append("")
    if ctx["scorecard"]:
        s = ctx["scorecard"]
        t.append(f"검증 스코어({s['rounds']}라운드): 블랙 {s['black']} · 화이트 {s['white']} · 레드 {s['red']} · 블루 {s['blue']}")
    if ctx["quality_note"]:
        t.append(ctx["quality_note"])
    if ctx["method_note"]:
        t.append(ctx["method_note"])
    t += ["", ctx["disclaimer"]]
    return ctx, "\n".join(t).strip() + "\n", unused


def _guess_dir(change) -> str | None:
    s = str(change or "").strip()
    if s.startswith(("+", "▲", "↑")):
        return "up"
    if s.startswith(("-", "−", "▼", "↓")):
        return "down"
    return "flat" if s else None


def _fmt_score(v) -> str:
    if isinstance(v, (int, float)):
        return f"{v:.1f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return "-"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True, help="briefing JSON path")
    ap.add_argument("--out-dir", default="out", help="output directory (default: out)")
    ap.add_argument("--check", action="store_true", help="validate only, do not write files")
    args = ap.parse_args()

    try:
        data = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(json.dumps({"ok": False, "errors": [f"파일 없음: {args.inp}"]}, ensure_ascii=False))
        return 2
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "errors": [f"JSON 문법 오류: {e}"]}, ensure_ascii=False))
        return 1

    errors, warnings = validate(data)
    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "opinion_chars": char_count((data.get("opinion") or {}).get("body")),
        "articles": len(data.get("articles") or []),
        "glossary_terms": len(data.get("glossary") or []),
    }
    if errors:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        print(json.dumps({"ok": False, "errors": ["jinja2가 필요합니다: pip install jinja2"]}, ensure_ascii=False))
        return 2

    ctx, text, unused = build(data)
    if unused:
        warnings.append("본문에 등장하지 않아 주석 번호가 붙지 않은 용어: " + ", ".join(unused))
    report["subject"] = ctx["subject"]

    if not args.check:
        env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)),
                          autoescape=select_autoescape(["html"]), trim_blocks=False, lstrip_blocks=False)
        page = env.get_template(TEMPLATE_NAME).render(**ctx)
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "newsletter.html").write_text(page, encoding="utf-8")
        (out / "newsletter.txt").write_text(text, encoding="utf-8")
        (out / "subject.txt").write_text(ctx["subject"] + "\n", encoding="utf-8")
        report["outputs"] = {k: str(out / k) for k in ("newsletter.html", "newsletter.txt", "subject.txt")}
        report["html_bytes"] = len(page.encode("utf-8"))
        if report["html_bytes"] > 95_000:
            warnings.append("HTML이 95KB를 넘습니다 — Gmail은 102KB 이상을 잘라서 보여 줍니다.")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
