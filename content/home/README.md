# still() 홈 페이지 — 11개 언어 정적 페이지

`python3 scripts/build_journal.py` 한 번이 저널과 홈을 같이 만든다(홈은 `scripts/build_home.py`). 홈만 다시 만들 땐 `python3 scripts/build_home.py`.

- 원본: `template.html`(영어 마크업, `data-i18n="키"`·`data-i18n-ph="키"`·`{{자리표시}}`) + `i18n.json`(언어별 문구, 없는 키는 영어로).
- 결과: `/<lang>/index.html` 13개(en ko ja zh es pt id ru vi fr de ar hi — ar 는 `dir="rtl"`) — 각자 `html lang`, 자기 자신 canonical, 그 언어 title·description·og:locale(+alternate), hreflang 13 + x-default. `/index.html` 은 x-default(영어 내용, canonical `/`).
- `/index.html`·`/<lang>/index.html` 은 **생성물** — 고치지 말고 template/i18n 을 고친다. 사이트맵 lastmod 는 빌드가 알아서 올린다 — `content/home/stamp.json` 에 template+i18n 해시와 날짜가 있고, 해시가 바뀌면 빌드가 오늘 날짜로 다시 쓴다(손으로 안 건드림; 빌드를 안 하면 `--check` 가 실패). `python3 scripts/build_home.py --check` 가 커밋된 결과와 새 빌드가 같은지 본다.
- **언어 규칙(전 ipe 웹 공통, Davy 2026-11-01)**: ① URL(`/xx/` 경로·`?lang=xx`) → ② 방문자가 고른 언어(`localStorage still_lang`) → ③ 브라우저 언어(`navigator.languages` 에서 처음 맞는 것, `ko-KR`→`ko`·`zh-TW`→`zh`·`pt-BR`→`pt`) → ④ 영어. 언어 중립 입구인 루트 `/`(와 저널 허브 `/journal/`)만 `<head>` 맨 위 JS(`site_common.AUTO_LANG_JS`)로 이 순서를 적용해 영어가 아닌 언어가 정해지면 `location.replace('/xx/'+쿼리+해시)` 로 보낸다(안내 띠 없음). 영어로 정해지면 루트에 그대로 둔다(루트=영어 페이지). `/xx/` 페이지는 절대 다른 언어로 보내지 않는다(①이 최우선). 로봇은 언어가 없어 루트에 남는다 — hreflang·canonical 은 그대로. `?lang=xx` 로 들어오면 그 언어를 저장한다.
- 다른 ipe 사이트로 가는 화면 링크는 그 페이지 언어를 넘긴다(`site_common.ipe_rest_url`: ipe.rest 가 경로를 가진 언어는 `https://ipe.rest/xx/`, 없는 `vi` 는 `https://ipe.rest/?lang=vi`). 원문(`content/info/pages.json`)에는 `(https://ipe.rest)` 로 두고 빌드가 바꾼다. JSON-LD 의 `@id`·`url` 은 그대로.
- 언어 선택(select)·푸터 언어 링크는 `localStorage still_lang` 에 저장하고 해당 언어 주소로 이동한다(저널·FAQ/소개 페이지도 같은 키).
- 번역 문구: en·ko 외 9개 언어는 브랜드 톤 기계번역, 원어민 검수 대기(정본: 결정 0087·0088 — 성경 구절은 언어별 퍼블릭 도메인 번역본).
- privacy·terms 는 en/ko 토글 페이지(`/privacy`, `/terms`) 그대로 — 푸터 링크는 모든 언어에서 `/privacy`.
- 루트(`/`, x-default)와 `/en/` 은 둘 다 영어라 title·description 이 같으면 중복 그룹이 된다 → `/en/` 만 `i18n.json` en 의 `page_meta_title`·`page_meta_desc` 로 따로 쓴다(다른 언어엔 이 키 없음). meta/og/twitter description 은 빌드가 문장 경계에서 160자 이내로 자른다(`site_common.meta_desc`, 화면 문구·JSON-LD 는 그대로).
- Google Fonts CSS 는 렌더를 막지 않게 `media="print" onload` + `<noscript>` 로 불러온다(`site_common.font_links`, 템플릿의 `{{FONT_LINKS}}`).
