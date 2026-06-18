import json

from search_visibility_auditor.validation import validate_audit_json


def test_validate_audit_json_detects_missing_fields(tmp_path):
    path = tmp_path / "audit.json"
    path.write_text(json.dumps({"audit_id": "x"}), encoding="utf-8")
    result = validate_audit_json(path)
    assert result["valid"] is False
    assert result["errors"]

