# 맥미니 디스패처 (launchd) — 예약 글을 제시간에 배포

GitHub 의 `schedule` cron 은 늦게 돈다(2026-10-24: 약 4h50m). 그래서 **맥미니가 주 트리거**다: 5분마다 `scripts/dispatch_due.py` 가
`publish_at` 이 지난 글의 라이브 URL(`https://still.ipe.rest/journal/<lang>/<slug>/`)을 확인하고, 404 가 있으면 `gh workflow run deploy.yml` 을 **한 번** 건다.
배포 워크플로의 cron(`45 0-3`·`45 7-9` UTC = 09:45~12:45·16:45~18:45 KST 매시 :45)은 늦을 수 있는 백업.

## 동작 규칙
- 대상: `publish_at <= 지금`, `draft` 아님, 72시간 이내(`--max-age-hours`). `published_at` 글(이미 공개)은 보지 않는다.
- 404 만 트리거(네트워크 오류·5xx 는 무시). 캐시된 404 를 피하려 `?_=<epoch>` 를 붙여 GET.
- 이미 `queued`/`in_progress` run 이 있거나 마지막 run 이 10분(`--cooldown-min`) 안에 만들어졌으면 걸지 않는다.
- 래퍼(`still_dispatch.sh`)는 창 밖(KST 09:00–12:40, 16:00–18:40 외)에는 바로 종료. `STILL_DISPATCH_ANYTIME=1` 이면 창 검사를 건너뛴다(수동 확인용).
- 런타임: 전용 읽기 클론 `~/.ipe/still-rest-dispatch`(없으면 clone, 매 실행 `git pull --ff-only`), 로그 `~/.ipe/logs/still-dispatch.log`.

## 설치 (레포 밖 파일 — 이 폴더는 템플릿 사본)
```
mkdir -p ~/.ipe/bin ~/.ipe/logs
cp scripts/launchd/still_dispatch.sh ~/.ipe/bin/still_dispatch.sh && chmod +x ~/.ipe/bin/still_dispatch.sh
GH_DIR="$(dirname "$(command -v gh)")"
sed -e "s|__HOME__|$HOME|g" -e "s|__GH_DIR__|$GH_DIR|g" scripts/launchd/rest.ipe.still-dispatch.plist > ~/Library/LaunchAgents/rest.ipe.still-dispatch.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/rest.ipe.still-dispatch.plist
launchctl print gui/$(id -u)/rest.ipe.still-dispatch | head
```
`gh auth status` 가 로그인돼 있어야 한다(키체인 인증). 내리기: `launchctl bootout gui/$(id -u)/rest.ipe.still-dispatch`.

## 확인
`STILL_DISPATCH_ANYTIME=1 ~/.ipe/bin/still_dispatch.sh --dry-run` — 실제 run 은 걸지 않고 무엇을 할지만 출력. 래퍼가 바뀌면 위 `cp` 를 다시.
