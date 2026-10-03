---
type: decision
title: 요양기관종류 r3 후속 — Docraft 기호 회귀 수정·정답지 표준값 통일
description: AWS r3 결과로 본 요양기관종류 후속 조치(Docraft f668ac9 push, 정답지 표준 4종 통일, 45314는 6f 이관)
tags: [요양기관종류, docraft, harness, golden, aws]
status: active
---

# 요양기관종류 r3 후속 — Docraft 기호 회귀 수정·정답지 표준값 통일

- 날짜: 2026-10-02
- 브랜치: Docraft `fix/institution-mark-answer` → dev `f668ac9`(origin·mlife push)
- 워크트리: Docraft `.worktrees/fix-institution-mark-answer`(병합 후 정리)

## r3 결과(하네스 6d30de5·Docraft 79a11bd, [[2026-10-02-aws-integrated-deploy-r3]])

| 문서 | 결과 | 원인 |
|---|---|---|
| 202501021624239c, 390b | 정답 | Docraft 채택(분기 7) |
| SA2019123045515 | 정답 | 하네스 d 정규화(고상급종합병원→상급종합병원) |
| SA2019123043735 | 정답(복구) | 체크 표시 정규화로 Docraft 일치(분기 5) |
| 390i, 400b | 오답(회귀) | Docraft 가 `V`만 반환 — 설명에 기호 목록을 늘어놓은 탓 |
| 45314 | 오답 | Docraft `[✓]병원급`을 하네스 `_drop_shared_evidence`가 버림 — mirae-assets-6f 가 수정 맡음 |
| 43806 | 오답 | Docraft 품질 SUSPICIOUS(no_source) — 다음 배포 보고 판단 |
| 39576 | 오답 | 의심 조건 미탐(명칭 없음·신뢰도 0.91) |

## 조치

- Docraft `f668ac9`: 요양기관종류 설명에서 기호 목록 제거, `ENUMS`에 표준 4종(`의원급·보건기관`·`병원급`·`종합병원`·`상급종합병원`)과
  동의어 추가 — 스키마가 4종만 허용, `[✓]병원급`→병원급, `V`→null. 654 passed. 사용자 승인으로 origin·mlife dev push.
- 정답지 표준값 통일(사용자 결정): `e2e/정답지/진료비영수증` `SA2019123157794`(병원→병원급), `SA2019123157840`(의원급,보건기관→의원급·보건기관).
  label_veiwer 번들 `20260930-1444-5491` golden 은 09:52에 이미 표준값(2020010684177 의원→의원급·보건기관, 157794 병원→병원급)이었다.
  수정 전 번들 golden 사본: 세션 scratchpad `golden-backup-5491`.

## 남은 것

- 다음 배포(담당 mirae-assets-6c)에 Docraft f668ac9 + 6f 의 `_drop_shared_evidence` 수정 포함 요청.
- unresolved 칸 산출 value 표준값 반영 — harness 9016c9f(사용자 결정: 반영), 1002d 배포 예정.

## r4 결과(Docraft f668ac9 단독 반영, 진료비영수증 30건, `e2e/out/golden1002-aws-r4`)

요양기관종류 golden 27칸 중 **25칸 정답**.

- 390i·400b: Docraft `병원급`(quality PASS) → 분기 7 채택. `V` 회귀 해소.
- 43806: Docraft `병원급` quality PASS(r3 SUSPICIOUS/no_source) → 분기 7 채택. c 방안 2(품질 판정 완화)는 불필요 — 닫는다.
- 202501021624239c·390b·45515·43735: 유지.
- 남은 오답 2: 39576(의심 조건 미탐, Docraft 미호출), 45314(r4는 Docraft /api/read HTTP 408 시한 초과로 재판독 없음. r3에선 `_drop_shared_evidence`로 빠짐 — 6f 수정 대기).
  45314 `value`가 `의원급`인 것은 harness 9016c9f(검토 칸 표준값 반영) 미배포 상태라서다(1002d 배포 예정).

## r5 결과(harness d8ce096·Docraft f668ac9, 59건, `e2e/out/golden1002-aws-r5`)

요양기관종류 출력 `value` 기준 27칸 중 25칸 정답(r4와 같음). 9016c9f 동작 확인 — 45314(unresolved)의 `value`가 AO 원값 `의원급`이
아니라 표준값 `의원급·보건기관`으로 나온다. 남은 오답 2칸:

- 45314: Docraft `/api/read` HTTP 408(시한 초과)이 r4·r5 연속 — 같은 호출에서 항목내역 표까지 읽어 오래 걸린다. 6f 의
  `_drop_shared_evidence` 수정 효과는 이 문서로 아직 확인하지 못했다.
- 39576: 의심 조건 미탐(명칭 없음·신뢰도 0.91) — 의심 문서만 Docraft 로 보내기로 한 결정의 한계.

## 최종(r8, 1002h: harness f9d417f·Docraft cba1b3b, `e2e/out/golden1002-aws-r8`)

요양기관종류 **28/29**(채점 29칸). 202501021624239c 종합병원·400b 병원급 복구(31401fa), 45314 병원급(335acb3 모호 출처 수용).
남은 1건 SA2019123039576 — 의심 조건 미탐(명칭 없음·신뢰도 0.91), 의심 문서만 Docraft 로 보내는 결정의 한계.
45314 표 요청 408(278초)로 끝수처리 행은 여전히 누락 — Docraft 표 판독 시간은 다른 세션 담당.

## r9(1002i: Docraft 298570b, harness f9d417f 유지)

요양기관종류 28/29 유지. 45314 표 요청 성공(Docraft 실패 3→0) → 선별급여 r15·끝수처리 r17 복원. 이 문서의 후속 과제는 39576(의심 미탐) 하나만 남았다.
