"""Custom YOLO weights are selected from models/detectors.json, not from code."""

import json

from bowlinger.pipeline.yolo_model import load_spec


def test_default_model_is_coco_person_and_sports_ball():
    spec = load_spec(name="coco")
    assert spec.name == "coco"
    assert spec.weights.name == "yolo11n.pt"
    assert spec.weights.is_file()
    assert spec.class_id("person") == 0
    assert spec.class_id("ball") == 32
    assert spec.provides("batsman") is True
    assert spec.provides("bowler") is True
    assert spec.provides("ball") is True
    assert spec.fallback_roles() == ["bat", "stumps"]


def test_cricket_becomes_the_default_only_when_its_weights_exist():
    spec = load_spec()
    weights = spec.config_path.parent / "cricket.pt"
    if weights.is_file():
        assert spec.name == "cricket"
        assert spec.class_id("ball") == 0
        assert 10 in spec.class_ids("stumps") and 11 in spec.class_ids("stumps")
    else:
        assert spec.name == "coco"


def test_named_cricket_map_points_at_a_drop_in_file(tmp_path, monkeypatch):
    config = tmp_path / "detectors.json"
    weights = tmp_path / "my-cricket.pt"
    weights.write_bytes(b"not a real model")
    config.write_text(
        json.dumps(
            {
                "active": "coco",
                "detectors": {
                    "nets": {
                        "weights": "my-cricket.pt",
                        "confidence": 0.2,
                        "classes": {"batsman": 1, "bowler": 2, "bat": 3, "ball": 4, "stumps": 5},
                        "roles": {
                            "batsman": "batsman",
                            "bowler": "bowler",
                            "bat": "bat",
                            "ball": "ball",
                            "stumps": "stumps",
                        },
                    }
                },
            }
        )
    )
    from bowlinger.config import Settings

    settings = Settings(db_path=tmp_path / "a.db", data_dir=tmp_path, model_config=config, model_name="nets")
    spec = load_spec(settings)
    assert spec.name == "nets"
    assert spec.weights == weights
    assert spec.fallback_roles() == []
    assert spec.class_id("stumps") == 5
    assert spec.confidence == 0.2
