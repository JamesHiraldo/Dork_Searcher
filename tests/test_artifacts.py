import csv

import pytest

from src.artifacts import derived_csv_path, ensure_distinct_paths, save_csv, save_json


def test_csv_path_never_reuses_json_path():
    assert derived_csv_path("report") == "report.csv"
    assert derived_csv_path("report.json") == "report.csv"


def test_colliding_artifact_paths_are_rejected(tmp_path):
    path = str(tmp_path / "report")
    with pytest.raises(ValueError):
        ensure_distinct_paths(path, path)


def test_artifacts_create_parents_and_neutralize_formulas(tmp_path):
    json_path = tmp_path / "nested" / "report.json"
    csv_path = tmp_path / "nested" / "report.csv"
    save_json(str(json_path), [{"value": "=cmd"}])
    save_csv(str(csv_path), ["value"], [{"value": "=cmd"}])

    assert '"=cmd"' in json_path.read_text(encoding="utf-8")
    with csv_path.open(newline="", encoding="utf-8") as source:
        assert next(csv.DictReader(source))["value"] == "'=cmd"
