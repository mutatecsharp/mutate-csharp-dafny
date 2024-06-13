#!/usr/bin/env python3.11
import argparse
import os
import subprocess
import sys
import signal

from collections import namedtuple
from loguru import logger
from pathlib import Path

SUPPORTED_FRAMEWORK = {"nunit", "mstest"}

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


def filter_choices(framework: str):
    if framework == "nunit":
        return "FullyQualifiedName"
    elif framework == "mstest":
        return "Name"
    raise NotImplementedError(f"Framework {framework} not supported")


def exit_if_tests_fail(framework: str, release_build: bool, testcases: list, test_project: Path):
    for test in testcases:
        if release_build:
            test_command = ["dotnet", "test", "--no-build", "-c", "Release",
                            f"--filter=\"{filter_choices(framework)}~{test}\"",
                            str(test_project)]
        else:
            test_command = ["dotnet", "test", "--no-build", f"--filter=\"{filter_choices(framework)}~{test}\"",
                            str(test_project)]
        logger.info("Running test {} with command {}", test, " ".join(test_command))
        result = run_subprocess(test_command, timeout_seconds=30)
        logger.info(result.stdout.decode('utf-8'))
        if result.stderr:
            logger.error(result.stderr.decode('utf-8'))
        if result.exit_code != 0:
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release_build", action="store_true", default=False)
    parser.add_argument("--framework", choices=SUPPORTED_FRAMEWORK, required=True)
    parser.add_argument("--passing-tests", type=Path,
                        required=True, help="Passing tests.")
    parser.add_argument("--test-project", type=Path, required=True,
                        help="Test project to validate against.")

    args = parser.parse_args()

    if args.framework not in SUPPORTED_FRAMEWORK:
        logger.error("Framework {} is not supported.", args.framework)
        exit(1)

    if not args.passing_tests.exists():
        logger.error("file does not exist. {}", str(args.passing_tests))
        sys.exit(1)

    if not args.test_project.resolve().exists():
        logger.error("test project does not exist. {}", str(args.test_project))
        sys.exit(1)

    test_file: Path = args.passing_tests

    with test_file.open() as f:
        testnames = f.readlines()

    exit_if_tests_fail(args.framework, args.release_build, testnames, args.test_project.resolve())
