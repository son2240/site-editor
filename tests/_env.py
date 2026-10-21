"""Import first in every test module: keeps tool settings and secrets out of the real home folder."""
import os
import sys
import tempfile
from pathlib import Path

HOME = Path(tempfile.gettempdir()) / f"site-editor-tests-{os.getpid()}"
os.environ["SITE_EDITOR_HOME"] = str(HOME)
os.environ["SITE_EDITOR_NO_KEYRING"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import atexit  # noqa: E402
import shutil  # noqa: E402

atexit.register(shutil.rmtree, HOME, True)
