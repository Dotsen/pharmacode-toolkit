"""Run the full benchmark into ./benchmark-output (same as `pharmacode benchmark`)."""

from __future__ import annotations

import sys

from pharmacode.cli import main

if __name__ == "__main__":
    sys.exit(main(["benchmark", *sys.argv[1:]]))
