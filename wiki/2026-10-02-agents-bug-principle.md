---
type: worklog
title: AGENTS.md에 버그·이슈 대응 원칙 추가
description: 모든 AGENTS.md에 "증상이 아니라 문제 유형을 해결한다" 절을 추가하고 저장소별로 반영한 내역
tags: [agents-md, 작업규칙, 버그대응]
status: active
---

- 날짜: 2026-10-02
- 브랜치: `docs/agents-bug-principle` (각 저장소)
- 워크트리: `.worktrees/agents-bug-principle` (각 저장소, 반영 후 정리. past-data-aiocr-api는 MR 대기로 유지)

## 내용

버그 수정 시 보고된 케이스만 통과시키지 않고 문제 유형 전체를 일반화해 고친다는 절을 추가했다.
절차 5단계(근본 원인 → 유형 정의 → 유사 사례 탐색 → 일반화된 수정 → 변형 케이스 테스트), 금지 사항(하드코딩 분기·에러 삼키기·기대값 맞추기·보고 위치만 수정), 과도한 일반화 경계, 완료 보고 4항목으로 구성된다.

## 반영 위치

| 파일 | 반영 | 비고 |
|---|---|---|
| `AGENTS.md` (상위 폴더) | 직접 수정 | git 저장소 아님 |
| `e2e/AGENTS.md` | 직접 수정 | git 저장소 아님 |
| harness-v2 | 로컬 dev `e7fe620` | 미push — 로컬 dev에 다른 세션의 미push 커밋 2개가 있어 push 보류 |
| Docraft | 로컬 dev `f5eff27` | 미push — 같은 이유(로컬 dev가 mlife/dev보다 3개 앞섬) |
| harness-installer | dev `5168d32` | origin(GitLab)·ps push 완료 |
| past-data-aiocr-api | 브랜치 `docs/agents-bug-principle` `7716f80` | 협업 저장소라 push만, MR 생성 필요 |

`past-data-aiocr-api/CLAUDE.md`는 문서 표지판 역할이라 손대지 않았다.
