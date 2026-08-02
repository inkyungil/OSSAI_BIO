"""루트 pyproject를 건드리지 않고 이 프로젝트의 src를 import 경로에 올린다.

각 script 첫 줄에서 `import _bootstrap`만 하면 된다. script를 직접 실행하면
Python이 script 폴더를 sys.path[0]에 넣으므로 이 모듈이 항상 먼저 잡힌다.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
