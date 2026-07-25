"""Shared subprocess runner with stdout tee (live print + capture)."""

import os
import signal
import subprocess
import sys
import threading
import time
from typing import List

from .base import RunResult

_IS_POSIX = os.name == "posix"


def _kill_tree(proc: subprocess.Popen):
    """Kill the child and (on POSIX) its whole process group, then reap it.

    Agentic CLIs fork grandchildren (shell tools, git, sandbox workers); killing
    only the direct child leaves those running and still mutating the repo.
    """
    try:
        if _IS_POSIX:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def run_with_tee(cmd: List[str], cwd: str, timeout: int = 600,
                 stdin_data: str = None, env: dict = None) -> RunResult:
    """Run subprocess, stream stdout/stderr to terminal, also capture for parsing."""

    captured_out: list = []
    captured_err: list = []

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.PIPE if stdin_data is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**os.environ, **(env or {})},
            start_new_session=_IS_POSIX,  # own process group so timeout can kill the whole tree
        )
    except FileNotFoundError as e:
        return RunResult(returncode=127, stderr=str(e))

    if stdin_data is not None:
        # Write on a thread — a large payload can fill the pipe buffer and
        # deadlock against the child's stdout otherwise.
        def writer():
            try:
                proc.stdin.write(stdin_data)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        threading.Thread(target=writer, daemon=True).start()

    def reader(stream, sink_list, dest):
        try:
            for line in iter(stream.readline, ""):
                sink_list.append(line)
                dest.write(line)
                dest.flush()
        finally:
            try:
                stream.close()
            except Exception:
                pass

    t_out = threading.Thread(target=reader, args=(proc.stdout, captured_out, sys.stdout), daemon=True)
    t_err = threading.Thread(target=reader, args=(proc.stderr, captured_err, sys.stderr), daemon=True)
    t_out.start()
    t_err.start()

    deadline = time.time() + timeout
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        if time.time() > deadline:
            _kill_tree(proc)
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            return RunResult(
                returncode=-1,
                stdout="".join(captured_out),
                stderr="".join(captured_err),
                timed_out=True,
            )
        time.sleep(0.1)

    t_out.join(timeout=2)
    t_err.join(timeout=2)

    return RunResult(
        returncode=proc.returncode,
        stdout="".join(captured_out),
        stderr="".join(captured_err),
    )
