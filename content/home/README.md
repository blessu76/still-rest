# still() 홈 페이지 — 11개 언어 정적 페이지

`python3 scripts/build_journal.py` 한 번이 저널과 홈을 같이 만든다(홈은 `scripts/build_home.py`). 홈만 다시 만들 땐 `python3 scripts/build_home.py`.

- 원본: `template.html`(영어 마크업, `data-i18n="키"`·`data-i18n-ph="키"`·`{{자리표시}}`) + `i18n.json`(언어별 문구, 없는 키는 영어로).
- 결과: `/<lang>/index.html` 11개(en ko ja zh es pt id ru vi fr de) — 각자 `html lang`, 자기 자신 canonical, 그 언어 title·description·og:locale(+alternate), hreflang 11 + x-default. `/index.html` 은 x-default(영어 내용, canonical `/`).
- `/index.html`·`/<lang>/index.html` 은 **생성물** — 고치지 말고 template/i18n 을 고친다. 문구를 바꾸면 `scripts/build_home.py` 의 `HOME_UPDATED` 날짜(사이트맵 lastmod)도 올린다. `python3 scripts/build_home.py --check` 가 커밋된 결과와 새 빌드가 같은지 본다.
- 방문자·로봇을 자동으로 보내지 않는다. 루트 `/` 에서만 저장된 선택(`localStorage still_lang`)·브라우저 언어를 보고 「한국어 →」 안내 띠를 띄운다(닫으면 세션 동안 숨김). 옛 `?lang=xx` 주소는 루트 `<head>` 맨 위 JS 로 `/xx/` 로 이동.
- 언어 선택(select)은 해당 언어 주소로 이동한다.
- 번역 문구: en·ko 외 9개 언어는 브랜드 톤 기계번역, 원어민 검수 대기(정본: 결정 0087·0088 — 성경 구절은 언어별 퍼블릭 도메인 번역본).
- privacy·terms 는 en/ko 토글 페이지(`/privacy`, `/terms`) 그대로 — 푸터 링크는 모든 언어에서 `/privacy`.
