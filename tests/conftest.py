# pytest bootstrap: the app modules live in ../app, not on the default path.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
