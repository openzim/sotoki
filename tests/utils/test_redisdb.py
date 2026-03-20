from unittest.mock import MagicMock, call, patch

import pytest

from sotoki.utils.database.redisdb import RedisDatabase
from sotoki.utils.shared import context


@pytest.fixture
def redis_db():
    """RedisDatabase instance with mocked Redis connection"""
    db = RedisDatabase.__new__(RedisDatabase)
    db.connections = {}
    db.pipes = {}
    db.nb_seens = {}
    db.should_commits = {}
    return db


def test_dump_uses_tmp_dir(redis_db):
    """dump() configures Redis dir to tmp_dir before saving"""
    mock_conn = MagicMock()
    with patch.object(
        type(redis_db), "conn", new_callable=lambda: property(lambda _: mock_conn)
    ):
        redis_db.dump()
    assert mock_conn.config_set.call_args == call("dir", str(context.tmp_dir))
    mock_conn.save.assert_called_once()


def test_dump_sets_dir_before_save(redis_db):
    """config_set(dir) must be called before save()"""
    call_order = []
    mock_conn = MagicMock()
    mock_conn.config_set.side_effect = lambda *_, **__: call_order.append("config_set")
    mock_conn.save.side_effect = lambda: call_order.append("save")
    with patch.object(
        type(redis_db), "conn", new_callable=lambda: property(lambda _: mock_conn)
    ):
        redis_db.dump()
    assert call_order == ["config_set", "save"]
