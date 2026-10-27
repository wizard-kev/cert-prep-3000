import os
import tempfile

# Point the app at a throwaway data directory before any ccst module is imported,
# so tests never touch the real question pool or tracker.
os.environ["CCST_DATA_DIR"] = tempfile.mkdtemp(prefix="ccst-test-")
os.environ["CCST_PROVIDER"] = "ollama"
