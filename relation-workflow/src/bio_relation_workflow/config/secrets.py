"""API key 값은 환경 변수에서만 읽는다."""

# 출처: OSSAI-26-1 저장소의 src/verifiable_ai_workflow/config/secrets.py에서 복사.
# 프로젝트를 C:\app\bio로 떼어내면서 두 곳을 고쳤다 — .env를 상위에서도 찾고,
# 어느 파일을 읽었는지 돌려준다. 원본은 project_root/.env 하나만 보고 없으면
# 조용히 넘어가는데, 그러면 다른 프로젝트의 .env를 우연히 쓰고도 모른다.

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 폴더에서 위로 몇 단계까지 .env를 찾는가. 저장소 루트에 하나만 두고
# 하위 프로젝트가 공유하는 배치를 허용하되, 무한정 올라가지는 않게 한다.
ENV_SEARCH_DEPTH = 2


def find_project_env(project_root: str | Path) -> Path | None:
    """프로젝트 폴더와 그 상위에서 .env를 찾는다. 없으면 None."""

    start = Path(project_root).resolve()
    for parent in (start, *list(start.parents)[:ENV_SEARCH_DEPTH]):
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_project_env(project_root: str | Path) -> Path | None:
    """프로젝트의 .env를 읽는다. 실제로 읽은 파일 경로를 돌려준다.

    이전에는 `project_root/.env` 하나만 보고, 없으면 조용히 아무것도 하지 않았다.
    그런데도 실행이 됐던 것은 의존성 하나가 인자 없는 `load_dotenv()`를 불러
    **현재 폴더에서 위로 올라가다 우연히** 다른 프로젝트의 .env를 집었기 때문이다.
    폴더를 옮기는 순간 깨지는 우연이라, 어디서 읽었는지 돌려주도록 바꿨다.
    """

    env_path = find_project_env(project_root)
    if env_path is not None:
        load_dotenv(env_path, override=False)
    return env_path


def require_api_key(env_name: str, *, env_path: Path | None = None) -> str:
    value = os.getenv(env_name)
    if not value:
        where = f" ({env_path}에서 읽었다)" if env_path else " (.env를 찾지 못했다)"
        raise ValueError(f"{env_name} 환경 변수가 필요합니다{where}")
    return value
