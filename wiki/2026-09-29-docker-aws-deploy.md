---
okf_version: "0.2"
type: implementation
title: Label Viewer Docker Compose·AWS 배포
description: 단일 docker-compose.yml로 로컬·AWS 배포를 지원하고, harness-v2 개발 서버에 이미지 반입 방식으로 올리는 deploy/aws 스크립트를 추가한 기록
tags: [label-viewer, deploy, docker, aws]
status: active
---

날짜: 2026-09-29
브랜치: `feat/docker-deploy`
워크트리: `label_veiwer/.worktrees/docker-deploy`

## 배경

배포 설정은 k8s 매니페스트뿐이었다. Docker만 있는 환경에서 바로 띄우고, harness-v2 AWS 개발 서버에서도 확인할 수 있게 한다.

## 구성

| 파일 | 역할 |
|---|---|
| `docker-compose.yml` | 단일 서비스. 볼륨 `data:/data`, 루프백 바인딩(`LABEL_VIEWER_BIND`), `/api/health` 헬스체크(python urllib — slim 이미지에 curl 없음) |
| `deploy/aws/.env.aws.example` | 접속 대상(harness-v2와 같은 EC2·키), `REMOTE_ROOT=/mnt/data/label-viewer`, 포트 |
| `deploy/aws/_common.sh` | env 로드, SSH/SCP, `remote_compose` |
| `deploy/aws/deploy.sh` | 로컬 빌드 → `docker save | gzip` → scp → `docker load` → `compose up --no-build --wait` |
| `deploy/aws/tunnel.sh` | `localhost:18765` → 서버 `127.0.0.1:8765` |
| `deploy/aws/logs.sh`, `down.sh` | 원격 로그, 정지(볼륨 보존) |

## 결정

- **harness-v2 방식 준용**: 서버에서 빌드하지 않고 이미지를 반입한다. 폐쇄망 설치와 같은 경로다.
- **compose 파일 하나**: 로컬과 서버가 같은 정의를 쓰고 차이는 `.env.aws` 값으로만 둔다. 오버레이 파일이 필요 없다.
- **루프백 전용**: 앱에 인증이 없고 이미지·JSON에 개인정보가 있을 수 있어 보안그룹을 열지 않고 SSH 터널로 접근한다.
- **데이터 디스크**: 서버 루트 디스크가 8.8GB라 `/mnt/data` 아래에 둔다. docker 볼륨은 docker 저장소(`/mnt/data`)에 생긴다.
- DB·GPU를 쓰지 않으므로 harness-v2의 provision·스키마·모델 단계는 없다. 서버에 docker·compose가 이미 설치돼 있다는 전제다.

## 검증

- 로컬 `docker compose up -d --build --wait`: 이미지 195MB, `healthy`, `/api/health` `{"ok":true}`, `/` 200.
- AWS 배포(2026-09-29): `LABEL_VIEWER_BIND=0.0.0.0`으로 배포, 컨테이너 `healthy`, 게시 `0.0.0.0:8765->8765`. 서버 안 `curl 127.0.0.1:8765/api/health` 정상.
- AWS 재배포(2026-09-29, dev `c0a9f11`): 양식 불일치·문서 종류 확정·분류 채점·비교 탭 문서 유형 행·반응형 레이아웃 반영. `deploy.sh`로 이미지 68MB 전송, 컨테이너 `healthy`. 외부에서 `/api/health` 정상, 정적 파일 `Cache-Control: no-cache`와 새 JS·CSS 확인.
- AWS 재배포(2026-09-29, dev `816753c`): 실행 응답 형식 Golden 초안 수정 반영. 컨테이너 `healthy`, `out_label_viewer.zip` 업로드 후 하네스 초안 생성 확인(진료비영수증, fields 5·groups 3·tables 1), 검증 번들 삭제.
- 외부 접속: 배포 직후 외부 요청은 타임아웃이었다. 서버에 firewalld가 없으므로 보안그룹 인바운드 TCP 8765를 열어야 한다.

## 외부 노출 주의

요청에 따라 서버를 `0.0.0.0`으로 바인딩했다. 앱에 인증과 TLS가 없으므로 보안그룹 소스 IP를 사무실·VPN 대역으로 제한한다. 루프백 전용으로 되돌리려면 `.env.aws`의 `LABEL_VIEWER_BIND=127.0.0.1`로 재배포한다.
