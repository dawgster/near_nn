"""Make ``cabal`` importable when pytest is run from anywhere in the repo."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
