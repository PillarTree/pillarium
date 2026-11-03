#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Pillarium entry point.

The window manager lives in the `pillarium` package (split across
focused modules); this script is a thin launcher so the old command
keeps working from anywhere on disk.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pillarium.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
