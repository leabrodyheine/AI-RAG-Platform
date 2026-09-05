"""Make the repository root importable so ``evaluation`` resolves under pytest.

The four services are installed editable, so their packages import without help.
The offline ``evaluation`` package is deliberately not installed (its
dependencies must never reach production images), so its parent directory is
placed on the path here.
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
