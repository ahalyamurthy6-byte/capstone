from __future__ import annotations

import sys
from pathlib import Path

from common.tracing import init_tracing

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

init_tracing("ui")
