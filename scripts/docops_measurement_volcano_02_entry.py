#!/usr/bin/env python3
"""One independently authorized Excel measurement after the scan cwd fix."""
from docops_measurement_validate_01_entry import VOLCANO_02_PROFILE, main


if __name__ == '__main__':
    raise SystemExit(main(profile=VOLCANO_02_PROFILE))
