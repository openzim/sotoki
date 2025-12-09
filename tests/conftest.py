#!/usr/bin/env python
"""Test configuration and fixtures for sotoki tests"""

import tempfile
from pathlib import Path

# Initialize context BEFORE any other sotoki imports
# This must happen at module import time, before pytest collects tests
# This is hence not done in a fixture
from sotoki.context import Context

tmpdir = tempfile.mkdtemp()
Context.setup(
    domain="test.stackexchange.com",
    mirror="https://archive.org",
    title="Test Site",
    description="Test description",
    output_dir=Path(tmpdir) / "output",
    tmp_dir=Path(tmpdir) / "build",
)
