"""Convenience root runner forwarding directly to facebook_lead_collector."""
import os
import sys
from pathlib import Path

# Change working directory and path to facebook_lead_collector
project_dir = Path(__file__).resolve().parent / "facebook_lead_collector"
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))
os.chdir(project_dir)

# Auto-detect & inject project virtualenv (.venv) if global python is used
try:
    import dotenv
except ImportError:
    venv_sites = list(project_dir.glob(".venv/lib/python*/site-packages"))
    if venv_sites:
        sys.path.insert(0, str(venv_sites[0]))

from main import main

if __name__ == "__main__":
    main()
