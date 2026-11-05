# 출력 계약 — `briefing.json`과 출력 파일

`scripts/render_newsletter.py`가 이 계약대로 검증한다. 전체 예시는 `assets/briefing.example.json`(수치·URL은 가상).

## 출력 파일 (`out/`)
| 파일 | 만드는 이 | 필수 |
|---|---|---|
| `ledger.json` | 블랙 (Step 1~2) | 예 |
| `debate_log.md` | 네 명 (Step 4~8) | 예 |
| `briefing.json` | 블루 (Step 7~8) | 발행일 |
| `newsletter.html`, `newsletter.txt`, `subject.txt` | 렌더러 | 발행일 |
| `SKIPPED.md` | 블랙 (Step 3) | 쉬는 날만 |
| `candidates.json` | `collect_news.py` | 네트워크가 열린 경우 |

## `briefing.json` 필드

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
| `date` | `YYYY-MM-DD` | ✅ | 발행일(KST) |
| `headline` | 문자열 | ✅ | 오늘의 한 줄. 45자 이내 권장 |
| `preheader` | 문자열 | | 받은편지함 미리보기, 90자 이내 |
| `greeting` | 문자열 | | 1~2문장 |
| `snapshot[]` | 객체 배열 | | `label`, `value` 필수 · `change`("+1.2%"), `change_dir`(up/down/flat, 생략 시 부호로 추정), `note`, `source_url`, `is_estimate`(true면 "추정" 배지 — 계산·추정값). 출처도 추정 표시도 없으면 경고 |
| `opinion.title` | 문자열 | | 기본 "오늘의 전문가 의견" |
| `opinion.body` | 문자열 | ✅ | **공백 포함 300~500자**(`**굵게**` 표시는 글자 수에서 빠짐, 연속 공백·줄바꿈은 1자). 빈 줄로 문단 구분 |
| `predictions[]` | 객체 배열 | 권장 | `label`, `value`, `basis` 필수(근거 없는 예측은 오류) · `confidence`(상/중/하). `basis` 120자 초과는 경고 |
| `qa[]` | 객체 배열 | | `q`, `a`. 2개 이하, 답 200자 초과는 경고 |
| `articles[]` | 객체 배열 | ✅ | **정확히 5개.** `title`, `source`, `published`(YYYY-MM-DD), `url`(http/https, 중복 금지), `summary` 필수 · `why`, `category`(`sources.md` §5 목록), `tier`(T1~T4). 발행일보다 미래 날짜는 오류, 7일 넘은 자료는 경고 |
| `shortfall_reason` | 문자열 | | 기준을 통과한 자료가 5개 미만일 때만. 이유를 독자에게 설명하는 문장 |
| `fact_check[]` | 객체 배열 | | `kind`(수정/주의/확인), `text`. 3개 이하 권장 |
| `glossary[]` | 객체 배열 | ✅ | `term`, `definition`. 최소 1개, 3~7개 권장, 10개 이하. `term`은 본문 표기와 똑같이 |
| `scorecard` | 객체 | ✅ | `black`, `white`, `red`, `blue`(0~10), `rounds`. 9 미만이 있으면 `quality_note` 필수 |
| `quality_note` | 문자열 | 조건부 | 최대 라운드 후에도 9점 미만인 항목이 있을 때 사유 한 줄 |
| `method_note` | 문자열 | | 수집 범위와 검토 건수 |
| `tagline`, `disclaimer` | 문자열 | | 기본값을 바꿀 때만 |

## 본문 서식
- `**굵게**` → 노란 형광펜 강조(단락당 1~2곳).
- 빈 줄 → 문단 나눔, 줄바꿈 → 줄바꿈.
- 용어 주석 번호는 렌더러가 단다. 본문에 `[1]` 같은 번호를 직접 쓰지 않는다.
  번호가 붙는 곳: `opinion.body`, `predictions[].basis`, `qa[].a`, `articles[].summary`·`why`, `fact_check[].text`(이 순서로 첫 등장).
  `headline`, `snapshot`, `predictions[].value`에는 붙지 않으니 쉬운 말로 쓴다.
- HTML 태그를 쓰지 않는다(모두 이스케이프됨).

## 렌더러 결과 읽기
```json
{"ok": true, "errors": [], "warnings": ["..."], "opinion_chars": 412, "articles": 5,
 "glossary_terms": 6, "subject": "[무신사 장외일보] 11/6(금) ...", "html_bytes": 36669}
```
- `ok: false`면 `errors`를 하나씩 고치고 다시 실행한다.
- `warnings`는 발행을 막지 않지만, 블루는 채점 때 경고를 하나씩 검토한다(특히 "본문에 등장하지 않아 주석 번호가 붙지 않은 용어").
