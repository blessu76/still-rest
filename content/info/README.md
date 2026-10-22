# content/info — FAQ + 「다른 Still 앱과 다릅니다」 페이지

- 원본: `pages.json` (언어 11개 × {FAQ 8문답, 소개 문단 2개, 제목·meta}). 빌드: `python3 scripts/build_journal.py` 가 `scripts/build_info.py` 를 불러 `/<lang>/faq/` · `/<lang>/about/` 22쪽 + sitemap(`info` 블록) + llms.txt 블록을 쓴다. 생성물은 손으로 고치지 않는다.
- 문구는 AI 초안(브랜드 톤) — **원어민 검수 대기**(홈 i18n 과 같은 상태). 사실(가격 US$3.99, 온디바이스, 구절은 사람이 검토·AI 생성 아님, iOS, 11개 언어)은 홈 카피·개인정보처리방침·llms.txt 와 같아야 한다 — 하나를 바꾸면 같이 바꾼다.
- `{L}` = 언어 폴더, `{psalm}`·`{verse}` = 홈 `i18n.json` 의 `hero_tag`·`verse_text`(언어별 시편 46:10). 링크는 `[글](url)`.
- FAQPage JSON-LD 는 화면에 보이는 질문·답과 글자 그대로 같다(테스트). `sameAs`·`downloadUrl` 은 App Store 페이지·프로필이 생기면 넣는다(지금은 넣지 않음).
- 개인정보처리방침은 **/privacy/ 한 장(en+ko)** 을 유지한다 — 법적 문서를 11개 언어로 기계 번역하지 않는다. FAQ 가 언어별로 요약해 /privacy/ 로 잇는다.
- `stamp.json` = `pages.json` 해시 + 날짜. 이 페이지들의 sitemap lastmod 이며 빌드가 알아서 갱신한다.
- 저널 글이 없는 동안은 이 페이지들의 머리·바닥에 Journal/RSS 링크가 없다(홈과 같은 규칙). 첫 글이 나가면 자동으로 생긴다.
