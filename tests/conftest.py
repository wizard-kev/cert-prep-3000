import os
import shutil
import tempfile
from pathlib import Path

# Point the app at a throwaway data directory before any certprep module is imported, so tests
# never touch the real question pools or progress. It holds a copy of the CCST certification's
# cert.json and objective files, with empty question pools.
_REAL_CERT = Path(__file__).resolve().parents[1] / "data" / "certs" / "ccst-cyber"
_DATA = Path(tempfile.mkdtemp(prefix="certprep-test-"))
_CERT = _DATA / "certs" / "ccst-cyber"
(_CERT / "questions").mkdir(parents=True)
shutil.copy2(_REAL_CERT / "cert.json", _CERT / "cert.json")
shutil.copytree(_REAL_CERT / "objectives", _CERT / "objectives")
os.environ["CERTPREP_DATA_DIR"] = str(_DATA)
os.environ.pop("CERTPREP_CERTS_DIR", None)
