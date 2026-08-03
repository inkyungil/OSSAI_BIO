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


# --- .env 탐색 ---
#
# 옮기기 전에는 `project_root/.env` 하나만 보고 없으면 조용히 넘어갔다. 그런데도
# live 실행이 됐던 것은 의존성 하나가 인자 없는 load_dotenv()를 불러 현재 폴더에서
# 위로 올라가다 **다른 프로젝트의** .env를 우연히 집었기 때문이다. 폴더를 옮기는
# 순간 깨지는 우연이라, 어디서 읽었는지 돌려주고 상위도 보도록 바꿨다.


def test_env_is_found_in_the_project_folder(tmp_path):
    from bio_relation_workflow.config import find_project_env

    (tmp_path / ".env").write_text("K=v\n", encoding="utf-8")
    assert find_project_env(tmp_path) == tmp_path / ".env"


def test_env_is_found_in_the_repository_root_above(tmp_path):
    """저장소 루트에 .env 하나만 두고 하위 프로젝트가 공유하는 배치."""
    from bio_relation_workflow.config import find_project_env

    (tmp_path / ".env").write_text("K=v\n", encoding="utf-8")
    nested = tmp_path / "relation-workflow"
    nested.mkdir()
    assert find_project_env(nested) == tmp_path / ".env"


def test_missing_env_is_reported_not_swallowed(tmp_path):
    from bio_relation_workflow.config import load_project_env

    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert load_project_env(deep) is None


def test_search_does_not_climb_forever(tmp_path):
    """무한정 올라가면 관계없는 프로젝트의 비밀값을 집는다."""
    from bio_relation_workflow.config import find_project_env

    (tmp_path / ".env").write_text("K=v\n", encoding="utf-8")
    too_deep = tmp_path / "a" / "b" / "c"
    too_deep.mkdir(parents=True)
    assert find_project_env(too_deep) is None


def test_missing_key_error_names_the_env_file(tmp_path):
    from bio_relation_workflow.config import require_api_key

    with pytest.raises(ValueError, match="찾지 못했다"):
        require_api_key("ABSENT_KEY_FOR_TEST", env_path=None)
    with pytest.raises(ValueError, match="에서 읽었다"):
        require_api_key("ABSENT_KEY_FOR_TEST", env_path=tmp_path / ".env")
