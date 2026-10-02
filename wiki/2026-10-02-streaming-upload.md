---
type: implementation
title: 업로드를 메모리에 올리지 않고 스트리밍으로 저장
description: 큰 번들 업로드 중 Pod가 메모리 한도(2Gi)를 넘겨 종료되고 브라우저에는 '네트워크 오류'만 보이던 문제를, 업로드를 임시 파일에서 바로 복사하도록 바꾸고 메모리 limit을 4Gi로 올려 해결한 기록
tags: [label-viewer, upload, memory, k8s, bug]
status: active
---

날짜: 2026-10-02
브랜치: `fix/streaming-upload`
워크트리: `.worktrees/streaming-upload`

## 증상

큰 번들을 업로드하던 중 연결이 끊기고 화면에 `네트워크 오류`만 떴다. 네트워크 timeout처럼 보였다.

## 근본 원인

- 업로드 경로에는 timeout이 없다. 브라우저 XHR은 timeout이 없고 uvicorn은 기본값을 쓰며 k8s는 NodePort로 바로 연결된다.
- 대신 업로드 내용을 통째로 메모리에 올렸다.
  - `backend/app.py`가 `await f.read()`로 모든 파일을 bytes로 모았다.
  - ZIP이면 `io.BytesIO`에 싸고 `zf.read`로 모든 항목을 한 번 더 메모리에 풀었다(`backend/bundle.py` `_iter_zip`).
- Pod 메모리 limit은 2Gi이고 uvicorn 워커 2개가 같이 쓰는데, 업로드 상한도 2048MB였다. 수백 MB만 올려도 OOMKilled로 Pod가 죽고, 브라우저에는 `xhr.onerror`의 `네트워크 오류`가 떴다.

## 문제 유형

크기에 상한이 큰 입력(업로드)을 스트림으로 다루지 않고 메모리에 전부 올린 것.

같은 유형을 찾아본 범위:
- 내보내기 ZIP(`backend/export.py`)은 이미 임시 파일에 쓰고 `StreamingResponse`로 보낸다. 해당 없음.
- 엑셀 내보내기의 `BytesIO`는 결과 크기가 작아 범위 밖이다.

## 수정

| 위치 | 변경 |
|---|---|
| `backend/app.py` 업로드 라우트 | `Content-Length`가 상한을 넘으면 본문을 받기 전에 413을 돌려준다. Starlette가 디스크로 스풀링한 `UploadFile.file`을 읽지 않고 그대로 넘기며, 복사는 `run_in_threadpool`로 이벤트 루프 밖에서 한다. 끝나면 `form.close()`로 임시 파일을 지운다. |
| `backend/bundle.py` `process_upload` | 파일 객체를 받아 seek로 크기를 잰다(`check_upload_size`는 라우트와 함께 쓴다). ZIP은 업로드 파일에서 바로 `ZipFile`을 열고 항목 이름(`ZipInfo`)만 모은다. |
| `backend/bundle.py` `_write_entries` | 항목을 하나씩 열어 `shutil.copyfileobj`로 복사한다. 손상·암호 항목은 400을 돌려주고, 실패하면 만들던 번들 디렉터리를 지운다. |
| `deploy/k8s/deployment.yaml` | `limits.memory` 2Gi → 4Gi. requests(512Mi)는 그대로 둔다. |

## 검증

- `pytest`: 55건 통과.
- 실측: 300MB ZIP(5MB 이미지 60장)을 uvicorn 워커 1개로 업로드하고 최대 RSS(VmHWM)를 비교했다.

| 코드 | 최대 RSS |
|---|---|
| 수정 전(dev `dd0f9bd`) | 691MB |
| 수정 후 | 79MB |

## 추가한 테스트

- `test_upload_bad_zip_entry_leaves_no_bundle`: 압축 데이터가 손상된 항목과 암호 항목은 400이고 번들을 남기지 않는다.
- `test_upload_content_length_over_limit_rejected_early`: 상한(1MB)을 넘는 업로드는 413이고 번들을 남기지 않는다.
- `test_upload_streams_without_loading_payload`: `UploadFile.read`를 막아도 20MB ZIP 업로드가 성공한다(메모리 적재 회귀 방지).
- 기존 `tests/test_bbox.py`의 `process_upload` 호출은 입력만 `io.BytesIO`로 바꿨다. 기대값은 그대로다.

## 남은 사항

- 업로드 임시 파일은 컨테이너의 `/tmp`(노드 임시 저장소)에 쌓인다. 2GB 업로드에는 노드 디스크 여유가 필요하다.
- 압축을 푼 크기에는 별도 상한이 없다(수정 전과 같음).
