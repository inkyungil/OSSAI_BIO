"""실행 설정 계약."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bio_relation_workflow.config import load_settings, project_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"


@pytest.mark.parametrize("name", ["relation.yaml", "relation-nim.yaml"])
def test_shipped_configs_validate(name):
    settings = load_settings(CONFIG_DIR / name)
    assert settings.artifact_schema_version == 2
    assert settings.limits.max_requests >= 103


@pytest.mark.parametrize("name", ["relation.yaml", "relation-nim.yaml"])
def test_config_paths_resolve_inside_project(name):
    settings = load_settings(CONFIG_DIR / name)
    for value in settings.paths.model_dump().values():
        assert project_path(PROJECT_ROOT, value).is_relative_to(PROJECT_ROOT)


def test_recorded_config_does_not_call_api():
    settings = load_settings(CONFIG_DIR / "relation.yaml")
    assert settings.provider.kind == "recorded"
    assert settings.provider.api_key_env is None


def test_live_config_declares_key_env():
    settings = load_settings(CONFIG_DIR / "relation-nim.yaml")
    assert settings.provider.kind == "litellm"
    assert settings.provider.api_key_env == "NVIDIA_NIM_API_KEY"
    assert settings.provider.api_base


def test_live_and_recorded_write_to_different_outputs():
    # 저장 응답 결과와 실제 응답 결과가 같은 폴더에 섞이면 안 된다.
    recorded = load_settings(CONFIG_DIR / "relation.yaml")
    live = load_settings(CONFIG_DIR / "relation-nim.yaml")
    assert recorded.paths.output != live.paths.output


def test_text_domain_needs_far_fewer_input_tokens():
    # 이미지가 없다. 원본 Week 1의 nvidia 설정은 250000이었다.
    live = load_settings(CONFIG_DIR / "relation-nim.yaml")
    assert live.limits.max_input_tokens <= 8000


def test_note_settings_have_no_render_options():
    settings = load_settings(CONFIG_DIR / "relation.yaml")
    assert set(settings.notes.model_dump()) == {
        "max_notes_per_case",
        "max_note_chars",
    }


def test_litellm_requires_key_env(tmp_path):
    payload = yaml.safe_load((CONFIG_DIR / "relation-nim.yaml").read_text("utf-8"))
    del payload["provider"]["api_key_env"]
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="api_key_env"):
        load_settings(path)


def test_unknown_key_is_rejected(tmp_path):
    payload = yaml.safe_load((CONFIG_DIR / "relation.yaml").read_text("utf-8"))
    payload["render_dpi"] = 150
    path = tmp_path / "extra.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(path)
