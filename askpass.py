#!/usr/bin/env python3
"""SSH_ASKPASS helper: prints the stored password for one target to OpenSSH.

OpenSSH runs this program when it needs a password; the secret comes from the OS
credential store (credstore.py) and only travels through this pipe to ssh."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import credstore  # noqa: E402

key = os.environ.get("SITE_EDITOR_SECRET", "")
secret = credstore.get_secret(key) if key.startswith("target:") else None
if not secret:
    sys.exit(1)
sys.stdout.write(secret + "\n")
