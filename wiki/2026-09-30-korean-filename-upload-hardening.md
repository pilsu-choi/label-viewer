---
okf_version: "0.2"
type: implementation
title: 한글 파일명 ZIP 인식과 업로드·조회 오류 전수 점검
description: Windows(CP949)·macOS(NFD) 압축의 한글 파일명 인식 수정과, 재배포 후 전수조사로 찾은 500 오류·업로드 제한 수정 기록
tags: [label-viewer, upload, unicode, hardening]
status: active
---

날짜: 2026-09-30
브랜치: `fix/korean-filename`, `fix/upload-hardening`
워크트리: `label_veiwer/.worktrees/korean-filename`, `label_veiwer/.worktrees/upload-hardening`

## 한글 파일명 인식 오류

| 증상 | 원인 | 수정 |
|---|---|---|
| Windows 탐색기 압축 ZIP의 문서 ID가 `┴°┤▄╝¡ 1`처럼 깨지고 `원본/`·`정답/` 폴더 JSON이 빠짐 | UTF-8 플래그 없는 ZIP 항목을 Python이 cp437로 읽음 | `_zip_name`: 원래 바이트를 UTF-8, 실패 시 CP949로 다시 읽음 |
| macOS 압축 파일명(NFD)이 한글 폴더 키와 안 맞고, 다른 출처 NFC 파일과 다른 문서로 갈림 | 유니코드 정규화 차이 | 업로드 경로를 NFC로 정규화 |

브라우저 폴더 업로드와 UTF-8 ZIP은 원래 정상이었다(한글로 시작하는 ID 목록·상세·이미지 확인).

## 전수조사 후 수정

| 문제 | 수정 |
|---|---|
| JSON 하나가 BOM·CP949·배열·`documents`에 비객체면 업로드와 `GET /api/bundles` 전체가 500, 남은 번들 때문에 첫 화면 목록이 계속 깨짐 | `read_json_text`(UTF-8 BOM 허용 → CP949), `load_json_safe`가 형식 오류를 문서 오류로 반환, `bundle_view` 비교 단계 예외를 문서 오류로 격리. `raw` 엔드포인트도 같은 디코딩 |
| 폴더 업로드 1001개 이상이면 400 `Too many files` | Starlette `request.form(max_files=100000)` |
| JSON 폴더의 `Thumbs.db`·`notes.txt`·이미지가 `.json`으로 저장돼 가짜 문서·500 | 종류별 확장자(JSON 폴더는 `.json`, 이미지 폴더는 이미지 확장자)만 저장 |
| 255바이트 넘는 파일명(한글 약 85자) 업로드 500, 빈 번들 잔존 | 저장 실패 시 번들 디렉터리 삭제 후 400 |
| `a..b` 같은 ID가 400으로 열리지 않고 번들 Excel 내보내기도 400 | `_safe_id`는 `.`·`..` 자체만 거부(`/`·`\`는 정규식이 이미 차단) |
| 손상·암호 ZIP 500 | 400 |
| 손상 TIF·BMP 이미지 500 | 422 |
| review·golden 요청 본문이 JSON 객체가 아니거나 셀이 객체가 아니면 500 | `json_body`, `_validate_golden` 형식 검사로 422 |
| OCR 값의 제어문자(`\x0b`)로 Excel 내보내기 500 | `ILLEGAL_CHARACTERS_RE` 제거 |

## 보류

- 같은 stem이 서로 다른 폴더·확장자로 중복될 때(`abc.png`+`abc.jpg`, `abc.p1.png`+`abc.p2.png`) `abc~2` 문서가 생기고 짝이 순서에 좌우된다. 고객 데이터 구조 확인 후 결정.
- `images/`처럼 종류 이름과 같은 최상위 폴더 아래 `x.golden.json`은 폴더 키가 우선해 빠진다. `ao_extract/` 안 `.aiocr.ui.json`을 AO로 보는 기존 규칙과 충돌해 순서를 바꾸지 않았다.
- 전체 묶음 ZIP은 메모리에서 만든다. 수 GB 번들이면 스트리밍 전환 필요.

## 검증

- `pytest` 42개 통과. `test_korean_zip_names`(CP949·NFD), `test_upload_hardening`(위 표 입력 일괄) 추가.
- 로컬 브라우저: 한글 ID 4건 목록·상세·이미지, 콘솔·HTTP 오류 없음.
