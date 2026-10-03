---
type: implementation
title: PostgreSQL 메타데이터 저장 도입
description: 파일 저장의 다중 워커 상태 관리 개선, 데이터 마이그레이션과 PostgreSQL 배포 구성
tags: [postgresql, migration, storage, export, golden]
status: active
---

날짜: 2026-10-03 · 브랜치: feat/postgresql → dev · 워크트리: .worktrees/postgresql

## 배경과 변경 범위

파일 기반 상태와 작업 잠금은 한 서버에서 동작하지만 여러 프로세스와 향후 서버 확장 시 메타데이터의 원자적 갱신과 작업 소유권 관리가 필요하다. 번들 검수 상태, Golden 이력, 내보내기 작업을 PostgreSQL로 옮겼다. 이미지·OCR JSON·현재 Golden JSON·내보내기 산출물은 기존 저장소에 남긴다.

- `backend/db.py`: psycopg 트랜잭션, namespace 격리, advisory lock, 테이블 생성 및 메타데이터 CRUD.
- 번들 상태는 DB를 기준으로 읽고 갱신한다. DB 장애 시 이전 `_state.json`으로 대체하지 않는다.
- Golden 변경은 DB 이력 저장과 함께 처리하며 실패 시 파일 바이트를 복원한다. 보상 처리까지 잠금을 유지한다.
- 내보내기 상태·취소·작업 수 제한·실행 슬롯은 DB로 공유한다. 작업 토큰과 heartbeat로 중단된 작업을 실패 처리한다.
- `backend/migration.py`, `scripts/migrate_postgres.py`: 재실행 가능한 파일 → DB 이관 및 DB → 파일 내보내기.
- 기존 DB 상태를 오래된 파일로 덮어쓰지 않는다. 전환 중 queued/running 작업은 실패로 이관하며 자동 재실행하지 않는다.
- DB 사용 시 `/api/health`가 DB 연결을 확인한다. 연결 오류는 API에서 503으로 응답한다.
- Docker Compose에 PostgreSQL 17과 영속 볼륨·healthcheck를 추가했다. Kubernetes는 StatefulSet·Service·PVC와 Secret 참조를 사용한다. 폐쇄망 반입에는 PostgreSQL 이미지도 포함한다.

## 실행과 롤백

환경 변수 `LABEL_VIEWER_DATABASE_URL`로 활성화한다. 로컬은 `--configure-local`로 저장소 `_database.json`에 연결 정보와 namespace를 권한 600으로 기록하여 기존 서버 실행 명령을 유지할 수 있다. 파일은 git에서 제외되는 저장소 내부에 둔다.

```bash
python scripts/migrate_postgres.py --data ./storage --dry-run
# 서버를 정지하고 DB 연결 환경 변수를 설정한 뒤 실행
python scripts/migrate_postgres.py --data ./storage --configure-local
python -m backend.app --data ./storage --port 8765
```

롤백은 서버를 정지한 뒤 `--export-files`를 실행하고 성공을 확인한 다음 DB 연결 환경 변수를 해제하고 `_database.json`을 안전한 백업 위치로 이동한다. 이관 명령은 원본 상태·이력 파일을 삭제하지 않는다. 이전 코드로 되돌릴 때도 먼저 최신 DB 상태를 파일로 내보낸다.

## 운영 제한

파일과 PostgreSQL은 하나의 분산 트랜잭션으로 묶이지 않는다. 처리 중 프로세스 강제 종료·호스트 장애가 발생하면 파일과 이력의 일관성을 확인해야 한다. 실행 중 DB 장애의 일반적인 예외 경로에는 파일 보상을 적용한다. DB와 파일 저장소를 함께 백업하며 일관된 백업은 쓰기 작업을 정지한 상태에서 수행한다.

메타데이터가 DB로 옮겨져도 여러 앱 인스턴스를 운영하려면 이미지·JSON·내보내기 파일을 공유하는 저장소가 필요하다. 현재 Kubernetes 앱은 기존 단일 replica/Recreate 구성을 유지한다. AWS 및 고객사 클러스터에는 이 세션에서 배포하지 않았다.

namespace는 이관·실행 환경에서 동일하게 설정한다. Compose/Kubernetes 기본값은 `label-viewer`이며 로컬 설정은 namespace도 보존한다. 업로드는 숨김 임시 디렉터리에서 준비하며 번들 생명주기 잠금으로 Golden 저장과 삭제를 조율한다.

## 검증

- 실제 PostgreSQL 17을 사용해 전체 pytest 125개 통과. 기존 101개와 PostgreSQL 통합·이관·동시성 회귀 24개를 포함한다.
- 회귀 범위: namespace 보존, 이관 재실행, UTF-8 BOM 원문 이력 복원, DB 장애 503, 설정 파일 권한, 저장/삭제 경합과 롤백, 업로드 가시성·ID 충돌, 다중 워커 작업 조회·취소·실행 슬롯·중단 작업 복구.
- Docker 이미지 빌드, Compose 설정 검사, Kustomize 렌더링, 설치 shell 문법 검사 통과.
- 임시 Docker 앱의 워커 2개에서 DB health·업로드·Golden 저장/이력·ZIP 생성/다운로드·번들 삭제 API 확인.
- 테스트 경고는 기존 Starlette/httpx/anyio 및 테스트의 fork 사용에 관한 deprecation이다. 백그라운드 작업의 미처리 예외 경고는 삭제 경합 수정 후 사라졌다.
