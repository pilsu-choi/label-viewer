---
type: implementation
title: 원장 명칭(master_reference) 상시 표시
description: 하네스 셀 evidence의 master_reference·candidates를 비교 탭 Harness 값 셀 아래 보조줄과 근거 팝오버 마스터 대조 영역에 표시한 기록
tags: [label-viewer, compare, evidence, master-reference]
status: active
---

날짜: 2026-10-02
브랜치: `feat/master-ref-view`
워크트리: `.worktrees/master-ref-view`

## 배경

하네스 `harness` 블록의 `master_reference: {system_id, code, name}`와 `candidates`는 백엔드가 `evidence`로 그대로 넘기지만 화면에는 나오지 않았다. 검수자가 hover 없이 "항목명과 원장 기준 명칭"을 대조할 수 있어야 한다.

## 변경

- `frontend/js/compare.js` `valueCell`: Harness 값 셀에 `evidence.master_reference.name`이 있으면 `원장(<code>) <name>`(code 없으면 `원장 <name>`) 보조줄을 항상 표시. 표시 전용이며 diff·배지·[채택]·채점과 무관. 키가 붙은 셀이면 항목명 셀 등 어디든 동일하게 동작.
- `evidencePopover` '마스터 대조': master·master_reference·candidates 중 하나라도 있으면 영역을 보여 주고 원장 명칭(명칭·코드·체계)과 후보 코드를 추가.
- `frontend/app.css`: `.cmp-master-ref`(기존 `--ink-3`, `--fs-xs` 토큰 사용, 다크모드 자동 대응).
- `scripts/make_dummy_bundle.py`: MC001 진찰료 행 항목 셀에 master_reference·candidates 추가.
- `tests/test_compare.py`: compare_doc이 master_reference·candidates를 evidence로 그대로 넘기는지(있음·code 없음·없음) 검증.
- API.md, README.md 설명 갱신.

## 한계

프론트 자동 테스트 체계가 없어 화면 표시는 코드 검토 수준이며 브라우저 확인은 하지 않았다. 후보가 객체인 경우 `code`→`name` 순으로 표시한다.

## Update (2026-10-02, `feat/name-row-master-ref`)

명칭 셀(`EDI명칭`·`병명`)에는 하네스 evidence가 없어 위 보조줄이 나오지 않았다. 같은 행 코드 셀의 master_reference를 `code_master_reference`로 복사해 표시하도록 보완했다. 더미 샘플의 master_reference는 항목 셀에서 DX002 `병명코드` 셀로 옮겼다. 자세한 내용은 [명칭 행 원장 명칭 표시](2026-10-02-name-row-master-ref.md).
