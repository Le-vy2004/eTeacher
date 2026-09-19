"""Convenience root runner forwarding directly to facebook_lead_collector."""
import os
import sys

# Change working directory and path to facebook_lead_collector
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "facebook_lead_collector"))
sys.path.insert(0, project_dir)
os.chdir(project_dir)

from main import main

if __name__ == "__main__":
    main()
