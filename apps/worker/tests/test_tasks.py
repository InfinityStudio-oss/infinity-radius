import os

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.tasks import ping  # noqa: E402


def test_ping_task_runs_eagerly() -> None:
    result = ping.apply()
    assert result.get() == "pong"
