#!/usr/bin/env python3
"""One fixed Excel measurement attempt through the registered Volcano route."""
from docops_measurement_validate_01_entry import VOLCANO_PROFILE, main


if __name__ == '__main__':
    raise SystemExit(main(profile=VOLCANO_PROFILE))
