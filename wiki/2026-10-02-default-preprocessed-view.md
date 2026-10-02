---
type: implementation
title: 이미지 기본 보기를 전처리로
description: 상세 이미지 뷰어와 목록 썸네일이 전처리 이미지를 먼저 고르고, 전처리 이미지가 없으면 원본을 고르게 바꾼 기록
tags: [label-viewer, image-viewer, preprocessed]
status: active
---

날짜: 2026-10-02
브랜치: `feat/default-preprocessed-view`
워크트리: `.worktrees/default-preprocessed-view`

## 변경

- `frontend/js/detail.js`: 문서를 열 때 `state.view`를 `doc.has.preprocessed ? 'preprocessed' : 'original'`로 정한다. 원본/전처리 토글과 `O` 단축키는 그대로다.
- `frontend/js/list.js`: 썸네일도 같은 순서로 고른다. 전처리 이미지를 불러오지 못하면 원본으로 다시 시도한다.
- `README.md`: 상세 화면 설명에 기본 보기 규칙을 적었다.

## 한계

브라우저에서 확인하지 않았고 코드만 검토했다. 백엔드 이미지 API는 바뀌지 않았다.
