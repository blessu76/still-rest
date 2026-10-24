# still() 저널 원고 형식 (11개 언어)

빌드: `python3 scripts/build_journal.py` (저널 + 홈 11개 언어를 한 번에). 검증만: `--check` (형식·안전 데이터 검사 + 커밋된 산출물이 최신인지). 초안 미리보기: 사이트 **복사본**에서 `--root /tmp/x --drafts`. 테스트: `python3 -m unittest discover -s tests`.

## 파일 구조와 URL

원고는 **`content/journal/<lang>/<slug>.md`** (폴더 = 언어, 파일명 = slug). 한 글의 모든 언어판은 **같은 slug**. 언어: `en ko ja zh es pt id ru vi fr de`.

| 구분 | 파일 | URL |
|---|---|---|
| 원문 (`translation_of` 없음 — ko 또는 en 만 가능) | `content/journal/ko/<slug>.md` | `/journal/ko/<slug>/` |
| 번역 (`translation_of: ko`) | `content/journal/<lang>/<slug>.md` | `/journal/<lang>/<slug>/` |

- 언어별 목록 `/journal/<lang>/` (그 언어 글이 1편 이상일 때만). `/journal/` = x-default 허브(원문 목록) · `/journal/feed.xml` = 원문 RSS.
- canonical = 자기 자신. hreflang = 그 글이 있는 언어 전부 + x-default(en, 없으면 ko), 서로 상호참조. 번역이 없는 언어는 페이지·sitemap·hreflang·llms.txt 어디에도 나오지 않는다.
- slug 는 `[a-z0-9-]+`, 언어 코드와 `feed` 는 쓸 수 없다. `?lang=` 은 쓰지 않는다.

## front matter

```
---
title: (그 언어 제목)
date: 2026-10-23               # KST 게시일. 번역본은 원문과 같은 날짜
slug: my-first-story            # 모든 언어판 동일, 파일명과 같게
lang: ko                        # 폴더 이름과 같아야 한다
description: (그 언어 한 문장)
category: 번아웃                # 그 언어의 자유 문구
bible_version: 개역한글(1961)   # 성경을 인용(> 인용 블록)하면 필수. 성경 인용이 아니면 `bible_version: none`
translation_of: ko              # 번역본만(ko·en 외 언어는 필수). 있으면 「AI 번역」 표시 + 원문 링크
draft: true                     # 선택: 어디에도 나가지 않음
publish_at: 2026-10-24 11:00    # 선택: 예약 발행(KST) — 이 시각이 지난 배포 빌드부터 공개 (date 와 같은 날이어야 함). 날짜 옆에 HH:MM 으로 보인다
published_at: 2026-10-23 18:18  # 선택: 이미 공개된 글이 실제로 올라간 시각(KST, publish_at 과 동시 사용 불가). 시각을 모르면 쓰지 않는다 → 날짜만 보인다
---
```

선택 칸: `updated`·`image`·`image_alt`·`keywords`·`citations`·`aliases`(옛 주소 → 정적 리다이렉트). 자세한 건 `scripts/build_journal.py` 맨 위 docstring. 샘플: `ko/sample-template.md` + `en/sample-template.md` (draft).
성경 번역본은 언어별 퍼블릭 도메인 본(결정 0088): en=WEB · ko=개역한글(1961) · ja=口語訳(1955) · zh=和合本(1919) · es=Reina-Valera 1909 · pt=Almeida · id=Terjemahan Lama · ru=Synodal · vi=Kinh Thánh 1926/1934 · fr=Louis Segond 1910 · de=Lutherbibel 1912.

## 🔴 안전 블록 (모든 글·모든 언어에 템플릿이 자동으로 붙인다)

글쓴이가 고치거나 뺄 수 없다 — 문구·번호는 전부 **`content/journal/safety.json`** 한 파일에서만 온다(원어민 검수 대상).

1. 제목 아래 띠: 「여러 사람의 경험을 엮어 쓴 이야기입니다」(창작 명시) + 「의료 조언이 아니며 진료·치료를 대신하지 않습니다」 + 위기 상자로 가는 링크.
2. 본문 뒤(글의 맨 끝): 성경 번역본 이름(`bible_version`) → 위기 상담 상자(`id="help"`: 안내문 + 나라별 번호 + findahelpline.com 폴백, 결정 D2) → 창작 명시 + 면책 한 줄 더. (모든 글에 붙는지는 테스트가 확인한다.)
3. 위기 문구에는 성경 구절·기도 권유를 넣지 않는다(CRISIS_PROTOCOL §2.2).

`safety.json`: `text.<lang>` = 문구 7개, `lines.<lang>` = `{status: draft|verified, regions: [{country, items: [{name, number, tel, hours, status, checked_on, source, note}]}]}`.
- **항목마다 `status`**: `verified`(공식 출처로 확인, `checked_on` 날짜 필수)인 번호만 글에 찍힌다. `draft` 는 후보로 파일에만 남고 화면에는 절대 나오지 않는다(`note` = 왜 아직 draft 인지). 확인된 번호가 하나도 없는 언어는 폴백 링크(findahelpline)만 보인다.
- `lines.<lang>.status` 는 언어 전체(문구+목록)를 원어민이 읽었는지 — `--strict-safety` 게이트가 이것을 본다.
**언어 단위 `status`: `ko` 는 2026-10-23 verified(Matt·still, Davy 위임), 나머지는 `draft`(원어민 미검수)**. 번호 항목은 2026-10-22 조사표(방 노트 20261022-221259)에서 「확인됨」인 것만 `verified`, 나머지는 `draft`(숨김). 월 1회 재확인 + 첫 글 전에 다시 본다. 원어민 검수 뒤 언어 `status` 를 `verified` 로, `--strict-safety` 가 이를 강제한다.

## 게시 절차

1. 원고(ko 원문 + 번역) 작성 → `python3 scripts/build_journal.py` (형식 오류를 빌드가 잡는다).
2. 게이트 — 하나라도 실패하면 커밋·배포 금지:
   `python3 -m unittest discover -s tests` · `python3 scripts/build_journal.py --check` · `python3 scripts/check_sitemap.py`
   **게시(공개 글이 1편이라도 있는 상태로 배포)할 때는 `--check --strict-safety` 도 통과해야 한다** — 그 글의 언어에 `draft` 위기 번호가 남아 있으면 실패. (배포 워크플로가 같은 검사를 돌린다.)
3. 발행 두 가지.
   ① 즉시: 글의 `draft: true` 줄을 지운다(`date` 가 그날이어야 함) → 빌드(`build_journal.py`) → 위 게이트 → 커밋·push.
   ② **예약(하루 2편, 무작위 시각)**: `draft: true` 대신 `publish_at: YYYY-MM-DD HH:MM`(KST)을 적어 한 번에 커밋·push 해 둔다. 시각은 **정각이 아니라 무작위** — 오전 한 편은 09:00~11:59, 오후 한 편은 16:00~17:59 안에서, 정각·:30 은 피하고 전날 같은 슬롯 시각과 15분 이상 벌어지게:
   `python3 scripts/pick_publish_time.py 2026-10-26 am` (오후는 `pm`; 오늘 글을 늦게 준비하면 `--not-before 16:40`). 출력 `YYYY-MM-DD HH:MM` 을 그대로 `publish_at` 에 붙인다. 한 글의 모든 언어판은 같은 시각.
   **제시간 발행은 맥미니 디스패처가 맡는다**: `scripts/dispatch_due.py` 가 5분마다(launchd, 창 안에서만) 시각이 지난 예약 글의 라이브 URL 을 확인해 404 가 있으면 `gh workflow run deploy.yml` 을 한 번 건다(이미 진행 중이거나 10분 안에 돈 run 이 있으면 걸지 않음). 설치·운영은 `scripts/launchd/README.md`. GitHub 의 schedule cron(09:45~12:45·16:45~18:45 KST 매시 :45)은 **늦을 수 있는 백업**일 뿐이다. 배포 워크플로는 push·수동 실행·cron 어느 쪽이든 러너에서 `build_journal.py --now <지금 KST> --strict-safety` 로 한 번 더 빌드해 시각이 지난 글만 Pages 에 올린다.
   그 빌드는 **커밋하지 않는다**: 커밋된 산출물(평소 `build_journal.py`·`--check`)은 시계와 무관하게 예약 글을 뺀 상태라 시간이 지나도 낡지 않는다. 예약 글을 레포 산출물에도 넣고 싶으면 `publish_at` 줄을 `published_at`(같은 값, date 유지)으로 바꿔 다시 빌드·커밋 — 날짜 옆 시각(HH:MM)이 유지된다. `draft: true` 가 있으면 `publish_at` 이 있어도 나가지 않는다. 로컬 확인: `python3 scripts/build_journal.py --now "2026-10-24 11:00"`(커밋하지 말 것 — `git checkout -- .` 로 되돌린다).
   ko 첫 발행 전: `safety.json` 의 `lines.ko.status` 를 원어민(Davy) 검수 뒤 `verified` 로 — 아니면 `--strict-safety` 가 막는다. 구절 인용(`>` 블록)은 앱 `daily_verses.json` 의 글자 그대로(테스트가 대조).
   보류 언어: `content/journal/hold.json`(지금 `id`) 에 적힌 언어는 `draft: true` 글만 둘 수 있다 — 공개 글이 있으면 빌드가 실패한다.
4. 커밋·push → 배포 후 `python3 scripts/check_sitemap.py --live` (모든 URL HTTP 200) → `python3 scripts/indexnow.py <새 URL…>`.

빌드가 대신 잡아 주는 것: 필수 칸 누락 · 폴더/`lang`/파일명 불일치 · 번역에 `translation_of` 없음/원문 없음/원문이 draft · 인용 블록인데 `bible_version` 없음 · 예약 slug · alias 중복 · 이미지 파일 없음 · 안전 데이터 누락(11개 언어 전부). `draft: true` 는 sitemap·llms·목록·hreflang 어디에도 나오지 않는다(테스트로 보장).
`content/`·`scripts/`·`tests/` 는 배포 산출물에서 제외된다(원고 .md 가 공개 URL 이 되지 않음).
