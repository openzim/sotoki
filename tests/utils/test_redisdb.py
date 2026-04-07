from unittest.mock import MagicMock, call, patch

import pytest
import redis.exceptions

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


def test_execute_pipe_with_retry_succeeds_first_attempt(redis_db):
    """_execute_pipe_with_retry() calls pipe.execute() once when no error occurs"""
    mock_pipe = MagicMock()
    redis_db._execute_pipe_with_retry(mock_pipe)
    mock_pipe.execute.assert_called_once()


def test_execute_pipe_with_retry_retries_on_connection_error(redis_db):
    """_execute_pipe_with_retry() retries after ConnectionError then succeeds"""

    mock_pipe = MagicMock()
    mock_pipe.execute.side_effect = [
        redis.exceptions.ConnectionError("reset"),
        None,
    ]
    with patch("threading.Event"):
        redis_db._execute_pipe_with_retry(mock_pipe, retries=5)
    assert mock_pipe.execute.call_count == 2


def test_execute_pipe_with_retry_exhausts_retries(redis_db):
    """_execute_pipe_with_retry() re-raises after exhausting all retries"""

    mock_pipe = MagicMock()
    mock_pipe.execute.side_effect = redis.exceptions.ConnectionError("reset")
    with patch("threading.Event"), pytest.raises(redis.exceptions.ConnectionError):
        redis_db._execute_pipe_with_retry(mock_pipe, retries=3)
    assert mock_pipe.execute.call_count == 3


def test_commit_retries_on_connection_error(redis_db):
    """commit() retries pipe.execute() on ConnectionError"""

    mock_pipe = MagicMock()
    mock_pipe.execute.side_effect = [
        redis.exceptions.ConnectionError("reset"),
        None,
    ]
    with (
        patch.object(
            type(redis_db), "pipe", new_callable=lambda: property(lambda _: mock_pipe)
        ),
        patch("threading.Event"),
    ):
        redis_db.commit()
    assert mock_pipe.execute.call_count == 2


def test_commit_done_retries_all_pipes(redis_db):
    """commit(done=True) retries execute() on all thread pipelines"""

    mock_pipe_a = MagicMock()
    mock_pipe_b = MagicMock()
    mock_pipe_a.execute.side_effect = [
        redis.exceptions.ConnectionError("reset"),
        None,
    ]
    mock_pipe_b.execute.return_value = None
    redis_db.pipes = {1: mock_pipe_a, 2: mock_pipe_b}

    with (
        patch.object(
            type(redis_db), "pipe", new_callable=lambda: property(lambda _: MagicMock())
        ),
        patch("time.sleep"),
        patch("threading.Event"),
    ):
        redis_db.commit(done=True)

    assert mock_pipe_a.execute.call_count == 2
    assert mock_pipe_b.execute.call_count == 1
