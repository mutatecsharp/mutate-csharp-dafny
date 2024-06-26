import os
import signal
import subprocess

from collections import namedtuple

# (exit_code: int, stdout: byte, stderr: byte, timeout: bool)
ProcessExecutionResult = namedtuple('ProcessExecutionResult', ['exit_code', 'stdout', 'stderr', 'timeout'])


def run_subprocess(args, timeout_seconds, cwd=None, env=None) -> ProcessExecutionResult:
    process = subprocess.Popen(args, start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                               env=env)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return ProcessExecutionResult(process.returncode, stdout, stderr, timeout=False)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        stdout, stderr = process.communicate()
        return ProcessExecutionResult(process.returncode, stdout, stderr, timeout=True)
