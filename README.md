# 무신사 장외일보 — 무신사 IPO·비상장주 데일리 브리핑 스킬

무신사 비상장 주식을 가진 사람이 매일 아침 3분 안에 **장외 시세 추이, 상장 예상 시점, 공모가, 실적 전망**을 파악하도록
돕는 Claude 스킬이다. 네 명의 AI 페르소나가 서로 묻고 검증하며 네 명 모두 9점(10점 만점) 이상을 줄 때까지 다듬은 뒤,
HTML 뉴스레터를 매일 07:00(KST)에 메일로 보낸다. 새 소식이 없는 날은 보내지 않는다.

| 페르소나 | 역할 |
|---|---|
| ⚫ 블랙 | 무신사 전담 IPO 애널리스트. 뉴스·공시·종목토론방·비상장 거래소를 훑고 상장 시점·공모가·상장 초기 시장가를 예측 |
| ⚪ 화이트 | 비상장주 투자자. 시세·추이·상장 시점·매도 가능 시점을 집요하게 질문 |
| 🔴 레드 | 재무·IR 관점 팩트체커(가상). 틀린 근거는 바로잡고 근거 없는 예측엔 경고 |
| 🔵 블루 | 뉴스레터 에디터. 300~500자 전문가 의견 + 자료 TOP 5 + 용어 풀이로 쉽게 정리 |

## 폴더 구조

```
.claude/skills/musinsa-ipo-daily-briefing/
├── SKILL.md                  # Role · Rubric · Context · Tools · Workflow · Guardrail
├── references/               # 기준 사실, 출처·쿼리, 예측 방법, 페르소나, 문체, 용어, 출력 계약
├── assets/                   # 이메일 HTML 템플릿, briefing.json 예시
├── scripts/
│   ├── collect_news.py       # 네이버 뉴스 API·구글 뉴스 RSS 후보 수집 (네트워크가 열린 곳에서)
│   ├── render_newsletter.py  # briefing.json → HTML/TXT/제목 + 형식 검증(300~500자, 자료 5개 등)
│   └── send_email.py         # Gmail SMTP 또는 Resend로 발송, 07:00까지 대기 옵션
└── evals/                    # 테스트 케이스 3개 (실전 실행, 잡음 필터·사실 교정, 소식 없는 날 건너뛰기)
.github/workflows/musinsa-daily-briefing.yml   # 매일 06:10 KST 생성 → 07:00 발송
```

## 바로 써 보기

이 레포를 연 Claude Code에서:

> 오늘자 무신사 장외일보 만들어줘. 메일은 보내지 말고 out/ 폴더에만 저장해줘.

`out/newsletter.html`이 미리보기다. 발송은 아래 자동화로 한다.

## 매일 07:00 메일 받기

### 방법 A — GitHub Actions (권장)

GitHub 서버에서 매일 06:10(KST)에 Claude가 뉴스레터를 만들고, 07:00에 메일을 보낸다. 네트워크 제한이 없어
뉴스 수집 스크립트와 Gmail 발송이 그대로 동작한다.

1. **기본 브랜치에 병합** — GitHub의 예약 실행은 기본 브랜치에 있는 워크플로만 돈다.
2. **Gmail 앱 비밀번호** — Google 계정 → 보안 → 2단계 인증을 켠 뒤 '앱 비밀번호'에서 16자리 비밀번호를 만든다.
3. **Claude 인증** — 둘 중 하나.
   - Claude Pro/Max 구독: 내 컴퓨터의 Claude Code에서 `claude setup-token`을 실행해 토큰을 받는다.
   - Anthropic API 키: console.anthropic.com에서 발급(실행할 때마다 사용량만큼 과금).
4. **Secrets 등록** — 레포 Settings → Secrets and variables → Actions → New repository secret

   | 이름 | 값 |
   |---|---|
   | `NEWSLETTER_TO` | 받을 메일 주소 |
   | `GMAIL_ADDRESS` | 보내는 Gmail 주소 |
   | `GMAIL_APP_PASSWORD` | 2번의 앱 비밀번호 |
   | `CLAUDE_CODE_OAUTH_TOKEN` 또는 `ANTHROPIC_API_KEY` | 3번의 값 |
   | (선택) `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | developers.naver.com 검색 API — 국내 기사 수집 품질이 좋아진다 |

5. **시험 실행** — Actions 탭 → "무신사 장외일보" → Run workflow. `send`를 끈 채 한 번 돌려 로그를 확인하고, 켜서 한 번 더 돌리면 메일이 온다.

### 방법 B — Claude Code 예약 작업 (클라우드)

GitHub Actions 대신 Claude Code의 예약 작업으로 돌릴 수도 있다. 이때 클라우드 샌드박스는 기본적으로 외부 접속이
제한되고 메일 서버(SMTP) 포트가 막혀 있으므로 다음이 필요하다.

1. 클라우드 환경 설정 → Network access에서 `api.resend.com`을 허용한다. 수집 품질을 높이려면 `news.google.com`,
   `openapi.naver.com`, `www.ustockplus.com`, `www.seoulexchange.kr`, `dart.fss.or.kr`, `kind.krx.co.kr`도 허용한다.
2. [Resend](https://resend.com)에 **받을 메일 주소로** 가입하고 API 키를 만든다. 도메인 인증 없이도 가입한 주소로는 보낼 수 있다.
3. 환경 변수에 `RESEND_API_KEY`, `NEWSLETTER_TO`를 넣는다.
4. Claude에게 "매일 06:10에 무신사 장외일보를 예약 발송 모드로 실행하는 예약 작업 만들어줘"라고 요청한다.

## 비용과 주의

- **비용**: 하루 한 번 웹 검색과 4인 검토를 하므로 실행당 수십만 토큰을 쓸 수 있다. 구독 사용량이나 API 요금을 확인한다.
  공개 레포는 GitHub Actions 사용 시간이 무료다.
- **공개 레포**: 이 레포는 공개 상태다. 받는 주소·API 키는 파일에 적지 말고 Secrets/환경 변수에만 둔다.
  지난 발행본은 레포가 아닌 Actions 캐시에만 보관한다. 개인적인 관심사가 드러나는 게 싫다면 레포를 비공개로 바꾸는 것을 권한다.
- **기준 사실 갱신**: `references/context.md`의 기준일이 오래되면(예: 예심 승인, 증권신고서 제출) 내용을 갱신한다.
  매일 실행이 토론 로그의 "유지보수 메모"에 고칠 점을 남긴다.
- **면책**: 공개 자료 기반 자동 리서치 요약이며 투자 권유가 아니다. 페르소나는 가상의 AI 역할로 무신사 및 실존 인물과 관계없다.

## 디자인 고치기

메일 디자인은 `assets/newsletter_template.html`(색상은 맨 위 `c` 사전), 문체와 구성은 `references/newsletter-style.md`에서
바꾼다. 수정 후 예시로 확인:

```bash
python3 .claude/skills/musinsa-ipo-daily-briefing/scripts/render_newsletter.py \
  --in .claude/skills/musinsa-ipo-daily-briefing/assets/briefing.example.json --out-dir out
```
