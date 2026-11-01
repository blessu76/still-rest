# still.ipe.rest

still() — 성경 구절로 하루의 고단함을 푸는 앱의 랜딩 사이트. 정적 사이트(GitHub Pages), push 하면 GitHub Actions 가 배포한다.

## 빌드 (의존성 없는 파이썬 3.8+ 표준 라이브러리)

| 명령 | 하는 일 |
|---|---|
| `python3 scripts/build_home.py` | 홈 13개 언어(ar RTL 포함) 정적 페이지(`/`, `/<lang>/`) + 사이트맵·llms.txt 홈 블록 — 원본은 `content/home/` (자세한 건 그 README) |
| `python3 scripts/build_home.py --check` | 커밋된 홈 페이지가 새 빌드와 같은지 확인 |
| `python3 scripts/build_journal.py` | 저널(허브·언어별 목록·글·RSS) + 홈 + **FAQ·소개 페이지(`/<lang>/faq/`·`/<lang>/about/`, 원본 `content/info/pages.json`, 13개 언어)** 를 한 번에. 원고 `content/journal/<lang>/<slug>.md`, 형식·게시 절차는 `content/journal/README.md`. `--check` 는 검증 + 산출물 최신 여부, `--check --strict-safety` 는 배포 게이트(위기 번호 미확정이면 실패) |
| `python3 scripts/fetch_scripture.py` | 저널 글이 인용한 구절을 언어마다 퍼블릭 도메인 원문(ebible.org)에서 글자 그대로 가져와 `content/journal/scripture.json` 에 쓴다. `--verify` 는 다시 받아 대조 |
| `python3 scripts/journal_i18n.py status·brief·apply` | 번역판 현황 · 번역 지시서(Claude Code 세션용) · 번역판 인용 블록을 scripture.json 으로 다시 쓰기 — 절차는 `content/journal/README.md` 「번역」 |
| `python3 scripts/check_sitemap.py` | 사이트맵 검증(URL 누락·hreflang 상호 참조·페이지 존재). 배포 뒤 `--live` 로 전 URL HTTP 200 확인 |
| `python3 scripts/indexnow.py` | 배포 뒤 새 URL 을 IndexNow(Bing·Naver 등)에 알림 — 키 파일은 루트의 `<32hex>.txt`(공개 파일) |
| `python3 -m unittest discover -s tests` | 단위·회귀 테스트 |

생성물(`index.html`, `<lang>/index.html`)은 손으로 고치지 않는다. `content/`·`scripts/`·`tests/` 는 빌드 전용이라 배포물에서 빠진다(`.github/workflows/deploy.yml`).

## 방문 분석 (GA4)

이 웹사이트(앱 아님)는 **Google Analytics 4**(`G-XG4BH800J0`, ipe.rest 와 같은 속성)와 Cloudflare Web Analytics(쿠키 없음)로 방문을 잰다. 앱은 아무것도 수집하지 않는다 — `/privacy/` 가 앱 범위와 웹사이트 범위(2항)를 따로 적는다.

- 스니펫은 `scripts/site_common.py` 의 `GA_SNIPPET` **한 곳**. 생성 페이지는 `build_journal.head()` 와 홈 템플릿의 `{{GA_SNIPPET}}` 로, 손으로 쓴 페이지(`privacy/`, `terms/`, `404.html`)는 `<!-- ga4:start -->…<!-- ga4:end -->` 표지 사이에 `sync_static_ga()` 가 넣는다(`build_journal.py` 가 부른다). 표지 안은 고치지 않는다.
- localhost / 127.0.0.1 에서는 스니펫이 아무것도 보내지 않는다(로컬 미리보기가 방문으로 안 잡힘).
- 스니펫·분석 서비스를 바꾸면 같이 고친다: `/privacy/` 2항(영·한), `content/info/pages.json` FAQ 답, `llms.txt`.
- 새 HTML 페이지를 손으로 만들면 `site_common.STATIC_PAGES` 에 더한다(`tests/test_ga4.py` 가 빠진 페이지를 잡는다).
