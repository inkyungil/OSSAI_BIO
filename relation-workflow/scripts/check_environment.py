"""Python, 필수 package와 이 프로젝트 package import를 확인한다.

의존성은 저장소 루트의 .venv를 그대로 재사용한다. 텍스트 도메인이라 원본 Week 1이
쓰는 pypdfium2·pillow는 필요하지 않다.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import sys

import _bootstrap

PACKAGES = (
    "pydantic",
    "pyyaml",
    "python-dotenv",
    "litellm",
    "deepeval",
)

MODULES = (
    "bio_relation_workflow",
    "bio_relation_workflow.config",
    "bio_relation_workflow.schemas",
    "bio_relation_workflow.preprocessing",
    "bio_relation_workflow.providers",
    "bio_relation_workflow.workflow",
    "bio_relation_workflow.evaluation",
    "bio_relation_workflow.xai",
)


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError(f"Python 3.12가 필요합니다: {sys.version.split()[0]}")

    print(f"Python: {sys.version.split()[0]}")
    print(f"project root: {_bootstrap.PROJECT_ROOT}")

    missing = []
    for name in PACKAGES:
        try:
            print(f"{name}: {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
    if missing:
        raise RuntimeError(f"설치되지 않은 package: {', '.join(missing)}")

    for name in MODULES:
        importlib.import_module(name)
    print(f"package import: {len(MODULES)}개 확인")

    print("환경 확인 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
