#!/usr/bin/env python3
"""TOOLSANDBOX-RESOURCE-PILOT-02 namespace entry.

Uses the existing single-attempt ToolSandbox lifecycle with a fixed P02 profile.
"""
from toolsandbox_resource_pilot_01_entry import PILOT_02_PROFILE, main


if __name__ == "__main__":
    raise SystemExit(main(profile=PILOT_02_PROFILE))
