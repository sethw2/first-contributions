"""Ensure the package is importable when running pytest from the project root."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
