"""실행값을 하나의 YAML에서 읽는다."""

# 출처: src/verifiable_ai_workflow/config/settings.py — 복사.
# 차이: PDF 렌더 설정(DocumentSettings)을 노트 설정(NoteSettings)으로 바꿨다.

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathSettings(SettingsModel):
    case_authoring: str
    cases: str
    prompt: str
    note_corpus: str
    candidates: str
    recorded_responses: str
    output: str


class NoteSettings(SettingsModel):
    """노트를 모델 입력으로 묶을 때의 상한. 텍스트라 렌더 설정이 없다."""

    max_notes_per_case: int = Field(default=10, gt=0)
    max_note_chars: int = Field(default=2000, gt=0)


class ProviderSettings(SettingsModel):
    kind: Literal["recorded", "litellm"]
    model: str = Field(min_length=1)
    api_key_env: str | None = Field(default=None, min_length=1)
    api_base: str | None = None
    structured_output: Literal["json_schema", "prompt_only"] = "json_schema"
    input_cost_per_token_usd: float | None = Field(default=None, ge=0)
    output_cost_per_token_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def cost_values_are_paired(self) -> ProviderSettings:
        if self.kind == "litellm" and not self.api_key_env:
            raise ValueError("실제 API provider에는 api_key_env가 필요합니다")
        values = (
            self.input_cost_per_token_usd,
            self.output_cost_per_token_usd,
        )
        if (values[0] is None) != (values[1] is None):
            raise ValueError("입력·출력 token 비용은 함께 설정해야 합니다")
        return self


class LimitSettings(SettingsModel):
    max_requests: int = Field(gt=0)
    requests_per_minute: int = Field(default=20, gt=0)
    max_retries: int = Field(default=3, ge=0)
    retry_initial_seconds: float = Field(default=5, gt=0)
    max_cost_usd: float = Field(gt=0)
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    max_wall_seconds: float = Field(gt=0)


class LabSettings(SettingsModel):
    artifact_schema_version: Literal[2] = 2
    paths: PathSettings
    notes: NoteSettings
    provider: ProviderSettings
    limits: LimitSettings


def load_settings(path: str | Path) -> LabSettings:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return LabSettings.model_validate(value)


def project_path(project_root: str | Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (Path(project_root) / path).resolve()
