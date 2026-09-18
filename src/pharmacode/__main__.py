"""Allow ``python -m pharmacode``."""

from __future__ import annotations

import sys

from pharmacode.cli import main

if __name__ == "__main__":
    sys.exit(main())
