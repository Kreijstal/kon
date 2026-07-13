from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from .config import get_config_dir

HeartbeatStatus = Literal["idle", "working", "running", "stopped"]

HEARTBEAT_INTERVAL_SECONDS = 15.0
HEARTBEAT_STALE_AFTER_SECONDS = 45.0


def _now() -> datetime:
    return datetime.now(UTC)


def _iso_now() -> str:
    return _now().isoformat()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _heartbeat_dir() -> Path:
    path = get_config_dir() / "heartbeats"
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass
class HeartbeatRecord:
    pid: int
    session_id: str
    cwd: str
    provider: str | None
    model: str | None
    status: HeartbeatStatus
    started_at: str
    last_activity_at: str
    last_heartbeat_at: str

    @property
    def is_pid_alive(self) -> bool:
        return _is_pid_alive(self.pid)

    def age_seconds(self, *, now: datetime | None = None) -> float:
        current = now or _now()
        return max(0.0, (current - _parse_timestamp(self.last_heartbeat_at)).total_seconds())

    def is_stale(self, *, stale_after_seconds: float = HEARTBEAT_STALE_AFTER_SECONDS) -> bool:
        return self.age_seconds() > stale_after_seconds or not self.is_pid_alive


class Heartbeat:
    def __init__(
        self,
        *,
        session_id: str,
        cwd: str,
        provider: str | None,
        model: str | None,
        status: HeartbeatStatus = "idle",
    ) -> None:
        self._pid = os.getpid()
        self._started_at = _iso_now()
        self._last_activity_at = self._started_at
        self._path: Path | None = None
        self._record = HeartbeatRecord(
            pid=self._pid,
            session_id=session_id,
            cwd=cwd,
            provider=provider,
            model=model,
            status=status,
            started_at=self._started_at,
            last_activity_at=self._last_activity_at,
            last_heartbeat_at=self._started_at,
        )
        self._path = self._record_path(session_id)
        self.beat(status=status, activity=True)

    @staticmethod
    def _record_path(session_id: str) -> Path:
        safe_session_id = "".join(c for c in session_id if c.isalnum() or c in {"-", "_"})
        return _heartbeat_dir() / f"{os.getpid()}-{safe_session_id}.json"

    @property
    def record(self) -> HeartbeatRecord:
        return self._record

    def update_identity(
        self, *, session_id: str, cwd: str, provider: str | None, model: str | None
    ) -> None:
        old_path = self._path
        new_path = self._record_path(session_id)
        self._record.session_id = session_id
        self._record.cwd = cwd
        self._record.provider = provider
        self._record.model = model
        self._path = new_path
        if old_path is not None and old_path != new_path:
            old_path.unlink(missing_ok=True)
        self.beat(activity=True)

    def beat(self, *, status: HeartbeatStatus | None = None, activity: bool = False) -> None:
        now = _iso_now()
        if status is not None:
            if status != self._record.status:
                activity = True
            self._record.status = status
        if activity:
            self._record.last_activity_at = now
        self._record.last_heartbeat_at = now
        self._write()

    def stop(self) -> None:
        self.beat(status="stopped", activity=True)

    def _write(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(asdict(self._record), handle, sort_keys=True)
                handle.write("\n")
            tmp_path.replace(self._path)
            self._path.chmod(0o600)
        finally:
            tmp_path.unlink(missing_ok=True)


def _read_record(path: Path) -> HeartbeatRecord | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        status = str(data["status"])
        if status not in {"idle", "working", "running", "stopped"}:
            return None
        return HeartbeatRecord(
            pid=int(data["pid"]),
            session_id=str(data["session_id"]),
            cwd=str(data["cwd"]),
            provider=data.get("provider"),
            model=data.get("model"),
            status=cast(HeartbeatStatus, status),
            started_at=str(data["started_at"]),
            last_activity_at=str(data["last_activity_at"]),
            last_heartbeat_at=str(data["last_heartbeat_at"]),
        )
    except Exception:
        return None


def list_heartbeats(
    *, include_stale: bool = False, stale_after_seconds: float = HEARTBEAT_STALE_AFTER_SECONDS
) -> list[HeartbeatRecord]:
    records: list[HeartbeatRecord] = []
    for path in _heartbeat_dir().glob("*.json"):
        record = _read_record(path)
        if record is None:
            continue
        if record.status == "stopped" and not include_stale:
            continue
        if record.is_stale(stale_after_seconds=stale_after_seconds) and not include_stale:
            continue
        records.append(record)
    records.sort(key=lambda record: record.last_heartbeat_at, reverse=True)
    return records


def cleanup_heartbeats(*, stale_after_seconds: float = HEARTBEAT_STALE_AFTER_SECONDS) -> int:
    removed = 0
    for path in _heartbeat_dir().glob("*.json"):
        record = _read_record(path)
        if (
            record is None
            or record.status == "stopped"
            or record.is_stale(stale_after_seconds=stale_after_seconds)
        ):
            path.unlink(missing_ok=True)
            removed += 1
    return removed
