import os
import tempfile
from pathlib import Path

# The server module builds its calibration store at import time: keep tests away from the real calibration.json.
os.environ.setdefault("PENARM_CALIBRATION", str(Path(tempfile.mkdtemp()) / "calibration.json"))
