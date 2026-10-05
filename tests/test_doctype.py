"""doctype 함수 및 apply_template 동작 검증."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.doctype import TEMPLATES, apply_template


class TestDiagnosisGroupFields:
    """진단 그룹에 진료소견 필드 존재 확인."""

    @pytest.mark.parametrize("doc_type", ["진단서", "입퇴원확인서", "소견서", "수술확인서"])
    def test_diagnosis_group_has_clinical_opinion(self, doc_type: str) -> None:
        """진단 그룹에 진료소견 필드가 포함되어 있는지 확인."""
        assert doc_type in TEMPLATES, f"{doc_type} not in TEMPLATES"
        template = TEMPLATES[doc_type]

        # 진단 그룹 찾기
        diagnosis_group = None
        for group in template.get("extracted_groups", []):
            if group.get("key") == "진단":
                diagnosis_group = group
                break

        assert diagnosis_group is not None, f"{doc_type} 템플릿에 진단 그룹이 없음"

        # 필드 확인
        field_keys = [f.get("key") for f in diagnosis_group.get("fields", [])]
        assert "진료소견" in field_keys, f"{doc_type}의 진단 그룹에 진료소견이 없음"

    @pytest.mark.parametrize("doc_type", ["진단서", "입퇴원확인서", "소견서", "수술확인서"])
    def test_diagnosis_group_has_required_fields(self, doc_type: str) -> None:
        """진단 그룹이 필수 필드를 모두 포함하는지 확인."""
        required = ["진단일", "최종진단", "임상적추정", "진료소견"]
        template = TEMPLATES[doc_type]

        diagnosis_group = None
        for group in template.get("extracted_groups", []):
            if group.get("key") == "진단":
                diagnosis_group = group
                break

        assert diagnosis_group is not None
        field_keys = [f.get("key") for f in diagnosis_group.get("fields", [])]

        for req_field in required:
            assert req_field in field_keys, f"{doc_type}의 진단 그룹에 {req_field}이 없음"


class TestApplyTemplate:
    """apply_template 함수 동작 검증."""

    def test_apply_template_adds_missing_clinical_opinion(self) -> None:
        """기존 정답지에 진료소견이 없을 때 빈 값으로 추가."""
        # 진료소견이 없는 문서
        doc = {
            "doc_type": "진단서",
            "extracted_fields": [],
            "extracted_groups": [
                {
                    "key": "진단",
                    "fields": [
                        {"key": "진단일", "value": "20240101"},
                        {"key": "최종진단", "value": "Y"},
                        {"key": "임상적추정", "value": "N"},
                    ]
                }
            ],
            "extracted_tables": []
        }

        result = apply_template(doc, "진단서")

        # 진단 그룹 찾기
        diagnosis_group = None
        for group in result.get("extracted_groups", []):
            if group.get("key") == "진단":
                diagnosis_group = group
                break

        assert diagnosis_group is not None

        # 진료소견 필드 확인
        clinical_opinion = None
        for field in diagnosis_group.get("fields", []):
            if field.get("key") == "진료소견":
                clinical_opinion = field
                break

        assert clinical_opinion is not None, "진료소견 필드가 추가되지 않음"
        assert clinical_opinion.get("value") == "", "진료소견 초기값이 빈 문자열이 아님"

    def test_apply_template_preserves_existing_clinical_opinion(self) -> None:
        """기존 진료소견 값이 보존되는지 확인."""
        existing_opinion = "환자의 상태가 호전되었습니다."
        doc = {
            "doc_type": "진단서",
            "extracted_fields": [],
            "extracted_groups": [
                {
                    "key": "진단",
                    "fields": [
                        {"key": "진단일", "value": "20240101"},
                        {"key": "최종진단", "value": "Y"},
                        {"key": "임상적추정", "value": "N"},
                        {"key": "진료소견", "value": existing_opinion},
                    ]
                }
            ],
            "extracted_tables": []
        }

        result = apply_template(doc, "진단서")

        # 진단 그룹 찾기
        diagnosis_group = None
        for group in result.get("extracted_groups", []):
            if group.get("key") == "진단":
                diagnosis_group = group
                break

        assert diagnosis_group is not None

        # 진료소견 필드 확인
        clinical_opinion = None
        for field in diagnosis_group.get("fields", []):
            if field.get("key") == "진료소견":
                clinical_opinion = field
                break

        assert clinical_opinion is not None
        assert clinical_opinion.get("value") == existing_opinion, "기존 진료소견이 보존되지 않음"

    @pytest.mark.parametrize("doc_type", ["진단서", "입퇴원확인서", "소견서", "수술확인서"])
    def test_apply_template_adds_clinical_opinion_for_all_diagnosis_types(self, doc_type: str) -> None:
        """4종 진단 문서 모두에서 진료소견이 추가되는지 확인."""
        doc = {
            "doc_type": doc_type,
            "extracted_fields": [],
            "extracted_groups": [
                {
                    "key": "진단",
                    "fields": [
                        {"key": "진단일", "value": "20240101"},
                    ]
                }
            ],
            "extracted_tables": []
        }

        result = apply_template(doc, doc_type)

        # 진단 그룹 찾기
        diagnosis_group = None
        for group in result.get("extracted_groups", []):
            if group.get("key") == "진단":
                diagnosis_group = group
                break

        assert diagnosis_group is not None

        # 필수 필드 모두 확인
        field_keys = [f.get("key") for f in diagnosis_group.get("fields", [])]
        required_fields = ["진단일", "최종진단", "임상적추정", "진료소견"]

        for req_field in required_fields:
            assert req_field in field_keys, f"{doc_type}에서 {req_field}이 없음"
