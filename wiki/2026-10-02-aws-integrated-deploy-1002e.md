---
type: worklog
title: AWS 통합 배포 1002e — label_veiwer 명칭 행 원장 표시·팝오버 화면 맞춤
description: label_veiwer 5284ded만 재배포하고 r5 세부내역서 1건을 새 묶음으로 올려 화면으로 확인(OCR·하네스 호출 없음)
tags: [aws, 배포, label_veiwer]
status: active
---

- 날짜: 2026-10-02 (취합 10:42~10:4x, 전원 회신으로 조기 진행)
- 배포 담당: mirae-assets-6c
- 워크트리: label_veiwer `.worktrees/deploy-1002e` (origin/dev 기준 detached, 배포 후 정리)
- 취합 기록·스크린샷: `e2e/out/aws-deploy-1002e/`

## 배포 내용

| 저장소 | 커밋 | 요청 세션 | 내용 |
|---|---|---|---|
| label_veiwer | origin/dev `5284ded` | harness-v2-74 | 명칭 행(EDI명칭·병명)에도 같은 행 코드 셀의 원장 보조줄·팝오버 '원장 명칭(같은 행 코드 기준)'. 팝오버 높이를 화면에 맞추고 넘치면 안에서 스크롤 |
| harness-v2 | 재배포 안 함 | 74 | dev `79c6eb7`(효과 없던 명칭 셀 동반 표기 코드 제거)은 출력 변화가 없어 다음 harness 배포 때 함께 올림 |

6f·f1은 '없음'. AWS 호출(OCR·하네스)은 없다.

## 확인

r5 세부내역서 SA2020010683943_3020010610445000을 새 묶음 `1002e-master-ref-check`(id `20261002-0143-182e`)로 올려 확인했다. 기존 묶음은 건드리지 않았다.

- ✔ 항목내역 #1 EDI명칭 행 하네스 값 아래 '원장(AA157) 초진진찰료-상급종합병원' 표시(EDI코드 행과 같은 보조줄). `viewer-name-row.png`
- ✔ EDI코드 팝오버가 화면 안에 들어와 위쪽이 잘리지 않음(높이 872px, 화면 1000px, 내부 스크롤 없음). 마스터 대조: 상태 found, 원장 명칭·코드·체계. `viewer-popover-code.png`
- ✔ EDI명칭 팝오버는 '원장 명칭(같은 행 코드 기준)'으로 표시. `viewer-popover-name.png`
- 후보 코드 줄은 이 행에 후보가 하나라 나오지 않았다.
