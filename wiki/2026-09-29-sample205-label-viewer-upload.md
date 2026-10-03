---
type: report
title: 표본 205건 label-viewer 업로드
description: 205건 AO UI 응답·하네스 결과·정답지를 out_label_viewer 양식으로 변환해 label-viewer에 올린 결과
tags: [label-viewer, golden, e2e, ui-response]
status: active
---

날짜: 2026-09-29  
브랜치: 해당 없음 — 루트·e2e는 Git 저장소가 아님(뷰어 수정은 label_veiwer `fix/doc-id-unicode` → dev 병합)  
워크트리: 해당 없음

## 결과

- 번들 `20260929-1627-2965`(`sample205_label_viewer`), 서버 `localhost:8765`: 205건, 원본·AO·하네스·정답지 누락 0건. 205건 모두 상세·이미지가 열리고, 좌표가 붙은 칸 9,502개, 하네스 근거가 붙은 칸 5,684개.
- 재현 스크립트: [make_label_viewer_bundle.py](../../e2e/make_label_viewer_bundle.py) (`e2e`에서 실행).

## 양식 비교

- AO: 수집본은 `{"documents":[stage]}` envelope. envelope만 벗기면 참고 양식(`out_label_viewer.zip`)과 key 구성이 같다.
- 하네스: 수집본은 API 형식(`documents[].extracted_*`)이고 참고 양식은 UI stage(`result.fields/groups/tables` + `harness`)다. 셀별 harness 블록을 UI 자리로 옮겼고, 재분류된 7건은 하네스 구조를 그대로 옮겼다. 정답지가 있는 11,991칸의 채점 결과가 변환 전후로 같았다.
- 한글·공백·괄호 파일명 107건이 뷰어 문서 ID 검사에 걸려 열리지 않아 뷰어를 고쳤다. 자세한 내용: [label_veiwer 기록](2026-09-29-unicode-doc-id.md).

## 주의

- 정답지는 AI 초안이다. 하네스 결과는 2026-09-24에 API 입력으로 돌린 것이다.
