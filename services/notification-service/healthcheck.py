#!/usr/bin/env python3
"""Container healthcheck — delegates to the shared healthcheck script."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "libs", "shared", "src"))

from shared.healthcheck import main

if __name__ == "__main__":
    sys.exit(main())
