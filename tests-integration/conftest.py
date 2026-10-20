import os
from pathlib import Path

import pytest
from zimscraperlib.zim import Archive

ZIM_FILE_PATH = Path(os.environ["ZIM_FILE_PATH"])


@pytest.fixture(scope="module")
def zim_file_path() -> Path:
    return ZIM_FILE_PATH


@pytest.fixture(scope="module")
def zim_fh() -> Archive:
    return Archive(ZIM_FILE_PATH)
