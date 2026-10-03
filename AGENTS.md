작업 내역은 상위 프로젝트 폴더 `/home/pilsu/projects/mirae-assets/wiki`에 우선 기록하고, 관련 저장소의 wiki에 동기화하라.

최신화는 dev 기준의 별도 브랜치·워크트리에서 진행한다. 다른 세션의 변경은 보존한다.

## wiki 기록과 동기화 우선순위

- 공통 작업 기록의 기준 위치는 `/home/pilsu/projects/mirae-assets/wiki`다. 작업 완료 보고 전에 이곳에 먼저 기록하고, 관련된 `harness-v2/wiki`·`Docraft/wiki`·`harness-installer/wiki`·`label_veiwer/wiki`에 동기화한다.
- 저장소에 먼저 작성한 기록은 상위 wiki에도 반영한다. 저장소 전용 상세 문서는 해당 wiki에 두되, 상위 wiki에 요약과 링크를 남겨 찾을 수 있게 한다.
- 본문뿐 아니라 상대경로로 참조하는 근거·첨부 파일, `wiki/index.md`, `wiki/log.md`도 함께 최신화한다. 색인·이력은 각 wiki의 기존 내용을 유지하며 필요한 항목을 추가한다.
- 같은 이름의 문서 내용이 다르면 양쪽의 근거와 변경 내역을 비교해 합친다. 저장소 전용 내용과 `deprecated` 상태를 일괄 덮어쓰지 않는다.
- 저장소 변경은 dev 기준의 별도 브랜치·워크트리에서 진행하고, 동기화 범위와 검증 결과를 날짜 prefix 문서에 기록한다.

