---
type: report
title: 10월 2일 Docraft·harness·label-viewer 작업 요약
description: 주간보고용 전일 작업 요약. 배포 검증 결과와 별도 브랜치 실험 결과를 구분한다.
tags: [weekly-report, docraft, harness, label-viewer]
status: active
---

날짜: 2026-10-03 (대상: 2026-10-02, KST)
브랜치: 해당 없음 — 저장소는 읽기 전용 조사, 상위 wiki에 요약만 기록
워크트리: 해당 없음 — 코드 변경 없음

## 보고용 요약

- **Docraft:** OCR·표 교정 결과 공유와 병렬 처리로 판독 지연 및 시간 초과 개선. AWS 검증에서 실패 3→0건, 처리시간 중앙값 129→86초. 표 추출·회전 보정도 개선했으며, 후속 보강안은 별도 브랜치 검증에서 정답지 59건 정확도 89.67→92.47%(10/2 기준 dev 반영 전).
- **harness:** 세부내역서의 열 밀림·요약행·소수점·누락값 보정과 요양기관종류 정규화, 영수증 전액 수납 규칙 개선. 최종 영수증 30건 AWS 검증 정확도 99.42%, 악화 0건. 추출 누락 검증 규칙도 추가했으며 AWS 검증은 대기.
- **label-viewer:** 원장 기준 명칭 표시·전처리 이미지 기본 보기로 검수 편의 개선. 문서 유형 표기 통일과 결과 없는 문서의 오채점 수정. 대용량 업로드를 스트리밍으로 전환해 300MB ZIP 실측 최대 메모리 691→79MB.

## 근거

- [Docraft 지연 분석](2026-10-02-docraft-read-latency-analysis.md)
- [표 추출 후속 검증](../../Docraft/wiki/2026-10-02-rowmajor-rotation-fixes.md)
- [harness r3 후속 보정](../../harness-v2/wiki/2026-10-02-r3-followups.md)
- [영수증 최종 AWS 검증](2026-10-02-aws-integrated-deploy-1002j.md)
- [추출 누락 검증 규칙](../../harness-v2/wiki/2026-10-02-추출-누락-검증-룰5-기대-칸.md)
- [원장 명칭 표시](2026-10-02-name-row-master-ref.md)
- [결과 없는 문서 채점 제외](2026-10-02-score-without-result.md)
- [스트리밍 업로드](2026-10-02-streaming-upload.md)

수치는 서로 다른 검증 범위의 결과이므로 저장소 사이에서 직접 비교하거나 누적 정확도로 합산하지 않는다.
