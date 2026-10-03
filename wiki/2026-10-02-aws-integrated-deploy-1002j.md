---
type: worklog
title: AWS 통합 배포 1002j — 전액 수납 납부할금액 빈칸 인정
description: harness cd1461a(규칙셋 2026.09.20)를 배포하고 진료비영수증 30건을 1회 돌려 r9 영수증과 비교
tags: [aws, 배포, harness, 진료비영수증, 테스트]
status: active
---

- 날짜: 2026-10-02 (취합 14:17~14:2x, 전원 회신으로 조기 진행)
- 배포 담당: mirae-assets-6c
- 워크트리: harness-v2 `.worktrees/deploy-1002j` (origin/dev 기준 detached, 배포 후 정리)
- 취합 기록: `e2e/out/aws-deploy-1002j/requests.md`

## 배포 내용

| 저장소 | 커밋 | 요청 세션 | 내용 |
|---|---|---|---|
| harness-v2 | origin/dev `cd1461a` (규칙셋 2026.09.20) | 6f | R-AC029-PAYABLE: 전액 수납(수납 합계 = 환자부담총액 − 이미납부)이면 납부할금액 빈칸(0)도 정상. 1002i 400b 악화 수정 |
| Docraft | `298570b` 유지 | - | - |

서버 `.env.aws` `RULE_SET_VERSION`을 2026.09.20으로 고쳤다. harness-installer `de72c78`은 기록만.

## 테스트 (진료비영수증 30건 1회, 실패 0) — `e2e/out/golden1002-aws-r10/`

- 범위: 변경이 영수증 규칙 1개라 30건만(6f·f1 동의). 정답은 5491 golden 현재본.
- r9 영수증 99.41% → r10 **99.42%**. 개선 1칸(400b 납부할금액 11000→0), 악화 0.
- 같은 유형(전액 수납·납부할 0) 5건 모두 일치 유지: 2020010684177, SA2019123157812, SA2019123157840, 공란다수_47809, 요양급여_44081.
- 요양기관종류 28/29 유지. Docraft 요청 12건 실패 0.
