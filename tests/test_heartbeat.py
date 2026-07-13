import json
import os
from datetime import UTC, datetime, timedelta

from kon.heartbeat import Heartbeat, cleanup_heartbeats, list_heartbeats


def test_heartbeat_writes_and_updates_identity(tmp_path, monkeypatch):
    monkeypatch.setattr("kon.heartbeat.get_config_dir", lambda: tmp_path)

    heartbeat = Heartbeat(
        session_id="abc123", cwd="/repo", provider="openai", model="gpt-5", status="idle"
    )

    records = list_heartbeats()
    assert len(records) == 1
    assert records[0].pid == os.getpid()
    assert records[0].session_id == "abc123"
    assert records[0].status == "idle"

    heartbeat.beat(status="working", activity=True)
    heartbeat.update_identity(
        session_id="def456", cwd="/repo/sub", provider="deepseek", model="deepseek-chat"
    )

    records = list_heartbeats()
    assert len(records) == 1
    assert records[0].session_id == "def456"
    assert records[0].cwd == "/repo/sub"
    assert records[0].provider == "deepseek"
    assert records[0].model == "deepseek-chat"


def test_cleanup_removes_stale_and_stopped_heartbeats(tmp_path, monkeypatch):
    monkeypatch.setattr("kon.heartbeat.get_config_dir", lambda: tmp_path)

    heartbeat = Heartbeat(
        session_id="live", cwd="/repo", provider="openai", model="gpt-5", status="idle"
    )
    heartbeat.stop()

    stale_dir = tmp_path / "heartbeats"
    stale_dir.mkdir(exist_ok=True)
    old = datetime.now(UTC) - timedelta(minutes=10)
    (stale_dir / "999999-stale.json").write_text(
        json.dumps(
            {
                "pid": 999999,
                "session_id": "stale",
                "cwd": "/repo",
                "provider": "openai",
                "model": "gpt-5",
                "status": "idle",
                "started_at": old.isoformat(),
                "last_activity_at": old.isoformat(),
                "last_heartbeat_at": old.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert len(list_heartbeats(include_stale=True)) == 2
    assert cleanup_heartbeats() == 2
    assert list_heartbeats(include_stale=True) == []
