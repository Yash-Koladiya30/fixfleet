"""Shared subprocess runner with stdout tee (live print + capture)."""

import os
import subprocess
import sys
import threading
import time
from typing import List

from .base import RunResult


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
            bufsize=1,
            env={**os.environ, **(env or {})},
        )
    except FileNotFoundError as e:
        return RunResult(returncode=127, stderr=str(e))

    if stdin_data is not None:
        try:
            proc.stdin.write(stdin_data)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

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
            proc.kill()
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
