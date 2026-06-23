import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tests.fixtures.build_fixture import build_fixture  # noqa: E402


@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("flighty") / "test.db")
    build_fixture(path)
    os.environ["FLIGHTY_DB_PATH"] = path
    os.environ.pop("FLIGHTY_USER_ID", None)
    yield path
