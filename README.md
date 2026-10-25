# still.ipe.rest

still() — 성경 구절로 하루의 고단함을 푸는 앱의 랜딩 사이트. 정적 사이트(GitHub Pages), push 하면 GitHub Actions 가 배포한다.

## 빌드 (의존성 없는 파이썬 3.8+ 표준 라이브러리)

| 명령 | 하는 일 |
|---|---|
| `python3 scripts/build_home.py` | 홈 11개 언어 정적 페이지(`/`, `/<lang>/`) + 사이트맵·llms.txt 홈 블록 — 원본은 `content/home/` (자세한 건 그 README) |
| `python3 scripts/build_home.py --check` | 커밋된 홈 페이지가 새 빌드와 같은지 확인 |
| `python3 scripts/build_journal.py` | 저널(허브·언어별 목록·글·RSS) + 홈 + **FAQ·소개 페이지(`/<lang>/faq/`·`/<lang>/about/`, 원본 `content/info/pages.json`, 11개 언어)** 를 한 번에. 원고 `content/journal/<lang>/<slug>.md`, 형식·게시 절차는 `content/journal/README.md`. `--check` 는 검증 + 산출물 최신 여부, `--check --strict-safety` 는 배포 게이트(위기 번호 미확정이면 실패) |
| `python3 scripts/fetch_scripture.py` | 저널 글이 인용한 구절을 언어마다 퍼블릭 도메인 원문(ebible.org)에서 글자 그대로 가져와 `content/journal/scripture.json` 에 쓴다. `--verify` 는 다시 받아 대조 |
| `python3 scripts/journal_i18n.py status·brief·apply` | 번역판 현황 · 번역 지시서(Claude Code 세션용) · 번역판 인용 블록을 scripture.json 으로 다시 쓰기 — 절차는 `content/journal/README.md` 「번역」 |
| `python3 scripts/check_sitemap.py` | 사이트맵 검증(URL 누락·hreflang 상호 참조·페이지 존재). 배포 뒤 `--live` 로 전 URL HTTP 200 확인 |
| `python3 scripts/indexnow.py` | 배포 뒤 새 URL 을 IndexNow(Bing·Naver 등)에 알림 — 키 파일은 루트의 `<32hex>.txt`(공개 파일) |
| `python3 -m unittest discover -s tests` | 단위·회귀 테스트 |

생성물(`index.html`, `<lang>/index.html`)은 손으로 고치지 않는다. `content/`·`scripts/`·`tests/` 는 빌드 전용이라 배포물에서 빠진다(`.github/workflows/deploy.yml`).
