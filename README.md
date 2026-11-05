# 무신사 장외일보 — 무신사 IPO·비상장주 데일리 브리핑 스킬

무신사 비상장 주식을 가진 사람이 아침 3분 안에 **장외 시세 추이, 상장 예상 시점, 공모가, 실적 전망**을 파악하도록 돕는
Claude 스킬이다. 네 명의 AI 페르소나가 서로 묻고 검증하며 **네 명 모두 9점(10점 만점) 이상을 줄 때까지** 다듬은 뒤,
HTML 뉴스레터를 **화~금 07:00(KST)** 에 메일로 보낸다. 새 소식이 없는 날은 보내지 않는다.

| 페르소나 | 역할 |
|---|---|
| ⚫ 블랙 | 무신사 전담 IPO 애널리스트. 뉴스·공시·종목토론방·비상장 거래소를 훑고 상장 시점·공모가·상장 초기 시장가를 예측 |
| ⚪ 화이트 | 비상장주 투자자. 시세·추이·상장 시점·매도 가능 시점을 집요하게 질문해 브리핑을 구체화 |
| 🔴 레드 | 재무·IR 관점 팩트체커(가상). 틀린 근거는 바로잡고 근거 없는 예측엔 경고 |
| 🔵 블루 | 뉴스레터 에디터. 300~500자 전문가 의견 + 자료 TOP 5 + 용어 풀이로 쉽게 정리 |

## 어떻게 돌아가나

```
화~금 06:10 KST  Claude Code 예약 작업
                 └ SKILL.md 절차 실행: 수집 → 출처 검증 → 발행 여부 판단 → 블랙 초안 → 화이트 질문
                   → 레드 팩트체크 → 블루 원고 → 4인 채점(모두 9점↑까지 최대 4라운드) → archive/날짜/ 커밋·push
07:00 KST        GitHub Actions(send-newsletter.yml)가 새로 올라온 newsletter.html 을 메일로 발송
새 소식 없는 날  archive/날짜/SKIPPED.md 만 남기고 메일은 보내지 않음
```

- **출처 필터**: '무신사' + 상장·IPO·실적·매출·기업가치·장외 등 주제어가 함께 있는 자료만 쓴다. 할인·신상·코디 같은 소비자 언급은 버린다.
- **검증 규칙**: 핵심 수치는 공시이거나 서로 다른 언론 두 곳이 일치해야 한다. 예측은 항상 '예측' 표시·근거·범위를 붙인다. 투자 권유는 하지 않는다.
- **연속성**: 지난 호(`archive/`)와 비교해 시세·예측이 무엇이 왜 바뀌었는지 쓴다. 화요일 호는 금~월 소식을 함께 다룬다.

## 폴더 구조

```
.claude/skills/musinsa-ipo-daily-briefing/
├── SKILL.md                  # Role · Rubric · Context · Tools · Workflow · Guardrail
├── references/               # 기준 사실, 출처·쿼리, 예측 방법, 페르소나, 문체, 용어, 출력 계약
├── assets/                   # 이메일 HTML 템플릿, briefing.json 예시
├── scripts/
│   ├── collect_news.py       # 네이버 뉴스 API·구글 뉴스 RSS 후보 수집 (네트워크가 열린 곳에서)
│   ├── render_newsletter.py  # briefing.json → HTML/TXT/제목 + 형식 검증(300~500자, 자료 5개 등)
│   └── send_email.py         # Gmail SMTP 또는 Resend로 발송, 07:00까지 대기 옵션, 로그의 주소 가림
└── evals/                    # 테스트 케이스 3개 (실전 실행, 잡음 필터·사실 교정, 소식 없는 날 건너뛰기)
archive/YYYY-MM-DD/           # 발행된 호(newsletter.html·briefing.json·토론 로그·출처 원장)
.github/workflows/
├── send-newsletter.yml       # archive 에 새 호가 올라오면 07:00 KST 발송
└── musinsa-daily-briefing.yml  # (대체 경로) GitHub 안에서 직접 생성·발송 — 손으로 실행할 때만
```

지난 호는 [`archive/`](archive/)에서 볼 수 있다. GitHub는 HTML을 코드로 보여 주므로, 파일을 내려받아 브라우저로 열면 메일과 같은 화면이 나온다.

## 메일 설정 (처음 한 번)

받는 주소·보내는 주소·비밀번호는 **저장소 Secrets** 에만 둔다. Secrets는 암호화되어 공개 레포에서도 아무도 볼 수 없고, 실행 로그에도 `***`로 가려진다.

1. **보내는 Gmail 계정의 앱 비밀번호 만들기** — Gmail은 일반 비밀번호로 프로그램이 메일을 보내는 것을 막아 두었다.
   - 보내는 계정으로 로그인해 <https://myaccount.google.com/signinoptions/two-step-verification> 에서 2단계 인증을 켠다.
   - <https://myaccount.google.com/apppasswords> 에서 이름(예: 무신사 장외일보)을 넣고 만들기 → 16자리 비밀번호를 복사한다.
   - 계정 비밀번호를 바꾸면 앱 비밀번호가 무효가 되니, 비밀번호를 바꿀 계획이면 먼저 바꾼 뒤 만든다.
2. **Secrets 등록** — 레포 Settings → Secrets and variables → Actions → **New repository secret** 을 세 번 누른다.

   | Name | Secret |
   |---|---|
   | `NEWSLETTER_TO` | 받을 메일 주소 |
   | `GMAIL_ADDRESS` | 보내는 Gmail 주소 |
   | `GMAIL_APP_PASSWORD` | 1번의 16자리 앱 비밀번호(공백 없이) |

3. **확인** — Actions → "무신사 장외일보 발송" → Run workflow → 최근 호 날짜(예: `2026-11-05`)를 넣고 실행하면 그 호가 바로 온다.

## 바로 써 보기

이 레포를 연 Claude Code에서:

> 오늘자 무신사 장외일보 만들어줘. 메일은 보내지 말고 out/ 폴더에만 저장해줘.

## 운영 메모

- **예약 작업**: Claude Code 예약 작업이 화~금 06:10 KST에 실행된다(Claude 앱의 예약 작업 목록에서 끄고 켤 수 있다).
- **기준 사실 갱신**: `references/context.md`의 기준일이 오래되면(예: 예심 승인, 증권신고서 제출) 갱신한다. 매 실행의 토론 로그 "유지보수 메모"에 고칠 점이 남는다.
- **비용**: 한 번 실행에 웹 검색과 4인 검토로 수십만 토큰을 쓸 수 있다.
- **디자인 고치기**: 메일 디자인은 `assets/newsletter_template.html`(색상은 맨 위 `c` 사전), 문체와 구성은 `references/newsletter-style.md`.
- **면책**: 공개 자료 기반 자동 리서치 요약이며 투자 권유가 아니다. 페르소나는 가상의 AI 역할로 무신사 및 실존 인물과 관계없다.
