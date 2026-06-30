"""Pytest configuration."""
import sys
import os

_here = os.path.dirname(__file__)
# Allow importing convsim_prompt without installing the package.
sys.path.insert(0, os.path.join(_here, "..", "src"))
# Allow importing test helper modules from the tests directory.
sys.path.insert(0, _here)
