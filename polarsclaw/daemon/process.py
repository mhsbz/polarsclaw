"""Daemon process management — start, stop, status via PID file."""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PID_FILE = Path.home() / ".polarsclaw" / "polarsclaw.pid"


class DaemonProcess:
    """Manage the PolarsClaw background daemon."""

    def __init__(self, pid_file: Path = DEFAULT_PID_FILE) -> None:
        self._pid_file = pid_file

    def start(self) -> None:
        """Fork a daemon process and write PID file."""
        if self._is_running():
            pid = self._read_pid()
            print(f"Daemon already running (PID {pid}).")
            return

        self._pid_file.parent.mkdir(parents=True, exist_ok=True)

        # First fork
        pid = os.fork()
        if pid > 0:
            # Parent — wait briefly then exit
            print(f"Daemon started (PID {pid}).")
            sys.exit(0)

        # Child — become session leader
        os.setsid()

        # Second fork to fully detach
        pid = os.fork()
        if pid > 0:
            sys.exit(0)

        # Grandchild — write PID and run
        self._pid_file.write_text(str(os.getpid()))

        # Redirect stdio to /dev/null
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(devnull)

        # Import and run the daemon loop
        from polarsclaw.config.settings import Settings
        from polarsclaw.daemon.runner import run_daemon

        import asyncio

        settings = Settings.from_file()
        asyncio.run(run_daemon(settings))

    def stop(self) -> None:
        """Stop the daemon: SIGTERM, wait 5s, then SIGKILL if needed."""
        pid = self._read_pid()
        if pid is None or not self._pid_exists(pid):
            print("Daemon is not running.")
            self._cleanup_pid()
            return

        print(f"Stopping daemon (PID {pid})...")
        os.kill(pid, signal.SIGTERM)

        # Wait up to 5 seconds
        for _ in range(50):
            time.sleep(0.1)
            if not self._pid_exists(pid):
                print("Daemon stopped.")
                self._cleanup_pid()
                return

        # Force kill
        logger.warning("Daemon did not stop gracefully, sending SIGKILL.")
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self._cleanup_pid()
        print("Daemon killed.")

    def status(self) -> str:
        """Check daemon status. Returns 'running' or 'stopped'."""
        pid = self._read_pid()
        if pid is not None and self._pid_exists(pid):
            return "running"
        if pid is not None:
            self._cleanup_pid()
        return "stopped"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_pid(self) -> int | None:
        if not self._pid_file.exists():
            return None
        try:
            return int(self._pid_file.read_text().strip())
        except (ValueError, OSError):
            return None

    def _is_running(self) -> bool:
        pid = self._read_pid()
        return pid is not None and self._pid_exists(pid)

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _cleanup_pid(self) -> None:
        try:
            self._pid_file.unlink(missing_ok=True)
        except OSError:
            pass
