import os
import time

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from fuzzing.util import constants
from fuzzing.util.mutant_status import MutantStatus
from fuzzing.util.run_subprocess import run_subprocess, ProcessExecutionResult


@dataclass(frozen=True)
class RegularDafnyCompileResult:
    success: bool
    elapsed_time: float
    artifact_absolute_path: Path


@dataclass(frozen=True)
class RegularDafnyBackendExecutionResult:
    execution_result: ProcessExecutionResult
    elapsed_time: float


@dataclass(frozen=True)
class MutatedDafnyCompileResult:
    status: MutantStatus
    artifact_absolute_path: Path


class DafnyBackend(Enum):
    # Supported
    JAVA = (1, True, "java", False, "{0}-java/{0}.java")
    JAVASCRIPT = (2, True, "js", True, "{0}.js")
    PYTHON = (3, True, "py", False, "{0}-py/__main__.py")
    CSHARP = (4, True, "cs", True, "{0}.dll")
    GO = (5, True, "go", False, "{0}-go/src/{0}.go")

    # Not supported
    CPP = (6, False, "cpp", "", None, None)
    RUST = (7, False, "rs", "", None, None)
    RESOLVED_DESUGARED_EXECUTABLE_DAFNY = (8, False, "dfy", None, None)

    def __init__(self,
                 identifier: int,
                 is_supported: bool,
                 target_flag: str,
                 artifact_in_place: bool,
                 artifact_relative_path: str,
                 execute_command: list):
        self.identifier = identifier
        self._is_supported = is_supported
        self._target_flag = target_flag
        # translated source code file in downstream language, relative to the artifact path
        self._artifact_in_place = artifact_in_place
        self._artifact_relative_path = artifact_relative_path
        self._execute_command = execute_command

    @property
    def target_flag(self):
        return self._target_flag

    @property
    def is_supported(self):
        return self._is_supported

    @property
    def artifact_in_place(self):
        return self._artifact_in_place

    @property
    def artifact_relative_path(self):
        return self._artifact_relative_path

    def execute_command(self, translated_src_file_path: Path):
        if self is DafnyBackend.JAVA:
            pass
        elif self is DafnyBackend.JAVASCRIPT:
            pass
        elif self is DafnyBackend.PYTHON:
            pass
        elif self is DafnyBackend.CSHARP:
            pass
        elif self is DafnyBackend.GO:
            pass

        raise NotImplementedError("DafnyBackend.execute_command is not implemented for this backend")

    # Pre: artifact_output_dir is suffixed with artifact_name
    # Note: tracing output does not change the semantics of the program, it only creates additional artifact.
    # Hence we pool the behaviour in the same method
    def regular_compile_to_backend(self,
                                   dafny_binary: Path,
                                   dafny_file_path: Path,
                                   artifact_output_dir: Path,
                                   artifact_name: str,
                                   timeout_in_seconds: int | float,
                                   trace_output_path: Optional[Path] = None) -> RegularDafnyCompileResult:
        if not self.is_supported:
            raise NotImplementedError()
        # Compiles the program with the Dafny compiler and produces artifacts that can be executed by the downstream
        # programming language.

        # Requirement: all artifacts are within artifact_output_dir. This allows for convenient deletion.
        artifact_dir = artifact_output_dir / artifact_name / artifact_name if self.artifact_in_place \
            else artifact_output_dir / artifact_name
        artifact_absolute_path = artifact_dir / self.artifact_relative_path.format(artifact_name)

        compile_command = ["dotnet", str(dafny_binary), "build", "--no-verify", "--allow-warnings",
                           f"--target:{self.target_flag}", "--output", str(artifact_dir),
                           str(dafny_file_path)]

        # Trace mutants
        if trace_output_path is not None:
            start_time = time.time()
            # Prepare environment variable to specify trace output path.
            env_dict = os.environ.copy()
            env_dict[constants.TRACER_ENV_VAR] = str(trace_output_path)
            (exit_code, stdout, stderr, timeout) = run_subprocess(compile_command, timeout_in_seconds, env=env_dict)
            elapsed_time = time.time() - start_time
        else:
            start_time = time.time()
            (exit_code, stdout, stderr, timeout) = run_subprocess(compile_command, timeout_in_seconds)
            elapsed_time = time.time() - start_time

        failed = False

        if exit_code != 0:
            failed = True
            print(f"""Skipping: error while compiling fuzz-d generated program with regu)
            Standard output:
            {stdout.decode('utf-8')}
            Standard error:
            {stderr.decode('utf-8')}
            """)
        elif timeout:
            failed = True
            print(
                f"Skipping: timeout while compiling fuzz-d generated program with the {('regular' if trace_output_path is None else 'traced')} Dafny compiler.")
        elif not artifact_absolute_path.is_file():
            failed = True
            print(
                f"Skipping: executable from Dafny compilation not found. ({('regular' if trace_output_path is None else 'traced')})")

        return RegularDafnyCompileResult(success=not failed, elapsed_time=elapsed_time,
                                         artifact_absolute_path=artifact_absolute_path)

    def regular_execution(self,
                          translated_src_path: Path,
                          timeout_in_seconds: int | float) -> RegularDafnyBackendExecutionResult:
        # Executes the binary resulting from Dafny compilation.
        execute_binary_command = self.execute_command(translated_src_path)

        start_time = time.time()
        runtime_result = run_subprocess(execute_binary_command, timeout_in_seconds)  # (exit_code, stdout, stderr, timeout)
        elapsed_time = time.time() - start_time

        if runtime_result.timeout:
            print(f"Skipping: timeout while running executable of generated program. (regular)")

        if runtime_result.exit_code != 0:
            print(f"Skipping: error while running executable of generated program. (regular)")

        return RegularDafnyBackendExecutionResult(execution_result=runtime_result, elapsed_time=elapsed_time)

    def mutated_compile_to_backend(self,
                                   dafny_binary: Path,
                                   dafny_file_path: Path,
                                   mutant_env_var: str,
                                   mutant_id: str,
                                   artifact_output_dir: Path,
                                   artifact_name: str,
                                   timeout_in_seconds: int | float) -> MutatedDafnyCompileResult:
        if not self.is_supported:
            raise NotImplementedError()
        # Compiles the program with the mutated Dafny compiler and produces artifacts that can be executed by the
        # downstream programming language.

        # Requirement: all artifacts are within artifact_output_dir. This allows for convenient deletion.
        artifact_dir = artifact_output_dir / artifact_name if self.artifact_in_place else artifact_output_dir
        artifact_absolute_path = artifact_dir / self.artifact_relative_path.format(artifact_name)

        compile_command = ["dotnet", str(dafny_binary), "build", "--no-verify", "--allow-warnings",
                           f"--target:{self.target_flag}", "--output", str(artifact_dir),
                           str(dafny_file_path)]

        # Prepare environment variable to instrument mutation.
        env_dict = os.environ.copy()
        env_dict[mutant_env_var] = mutant_id
        (exit_code, stdout, stderr, timeout) = run_subprocess(compile_command, timeout_in_seconds, env=env_dict)

        if timeout:
            mutant_status = MutantStatus.KILLED_COMPILER_TIMEOUT
        elif exit_code != 0:
            mutant_status = MutantStatus.KILLED_COMPILER_CRASHED
        elif not artifact_absolute_path.is_file():
            mutant_status = MutantStatus.KILLED_COMPILER_MISSING_EXECUTABLE_OUTPUT
        else:
            mutant_status = MutantStatus.SURVIVED_INTERNAL

        return MutatedDafnyCompileResult(mutant_status, artifact_absolute_path)

