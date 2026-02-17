from __future__ import annotations

import os

from shared.nexus_common.generic_demo_agent import build_generic_demo_app

app = build_generic_demo_app(default_name="care-coordinator", app_dir=os.path.dirname(__file__))
