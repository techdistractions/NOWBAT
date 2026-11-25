#!/usr/bin/env python3
"""Compatibility entry point: create the complete local-build packages."""
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    sys.exit(subprocess.call([sys.executable, '-B', str(Path(__file__).with_name('RELEASE.PY')), '--local-build']))
