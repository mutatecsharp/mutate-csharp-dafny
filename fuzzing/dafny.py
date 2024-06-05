import os
import time

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, List
from loguru import logger

from util import constants
from util.program_status import MutantStatus, RegularProgramStatus
from util.run_subprocess import run_subprocess, ProcessExecutionResult


@dataclass(frozen=True)
class RegularDafnyCompileResult:
    program_status: RegularProgramStatus
    elapsed_time: float


@dataclass(frozen=True)
class RegularDafnyBackendExecutionResult:
    program_status: RegularProgramStatus
    execution_result: ProcessExecutionResult
    elapsed_time: float


@dataclass(frozen=True)
class MutatedDafnyCompileResult:
    mutant_status: MutantStatus


@dataclass(frozen=True)
class MutatedDafnyBackendExecutionResult:
    mutant_status: MutantStatus


class DafnyBackend(Enum):
    # Supported
    JAVA = (1, True, "java", False)
    JAVASCRIPT = (2, True, "js", True)
    PYTHON = (3, True, "py", False)
    CSHARP = (4, True, "cs", True)
    GO = (5, True, "go", False)

    # Not supported
    CPP = (6, False, "cpp", False)
    RUST = (7, False, "rs", False)
    RESOLVED_DESUGARED_EXECUTABLE_DAFNY = (8, False, "dfy", False)

    def __init__(self,
                 identifier: int,
                 is_supported: bool,
                 target_flag: str,
                 artifact_in_place: bool):
        self.identifier = identifier
        self._is_supported = is_supported
        self._target_flag = target_flag
        # translated source code file in downstream language, relative to the artifact path
        self._artifact_in_place = artifact_in_place

    @property
    def target_flag(self):
        return self._target_flag

    @property
    def is_supported(self):
        return self._is_supported

    @property
    def artifact_in_place(self):
        return self._artifact_in_place

    def get_execute_command(self, artifact_dir: Path, file_name: str) -> List[str]:
        if self is DafnyBackend.JAVA:
            return ["java", "-cp",
                    f"{str(artifact_dir / file_name)}-java:{str(artifact_dir / file_name)}-java/DafnyRuntime.jar",
                    f"{artifact_dir / file_name}-java/{file_name}.java"]
        elif self is DafnyBackend.JAVASCRIPT:
            return ["node", f"{str(artifact_dir / file_name)}.js"]
        elif self is DafnyBackend.PYTHON:
            return ["python3", f"{str(artifact_dir / file_name)}-py/{file_name}.py"]
        elif self is DafnyBackend.CSHARP:
            return ["dotnet", f"{str(artifact_dir / file_name)}.dll"]
        elif self is DafnyBackend.GO:
            return [f"{str(artifact_dir / file_name)}"]

        raise NotImplementedError("DafnyBackend.execute_command is not implemented for this backend")

    # These errors have appeared in Dafny and not fixed since submission of these bugs by fuzz-d's original author.
    def get_known_compilation_errors(self) -> List[str]:
        if self is DafnyBackend.JAVA:
            return ["incompatible types", "incompatible bounds", "no suitable method", "lambda", "unreachable statement"]
        if self is DafnyBackend.CSHARP:
            return ["error CS1628", "error CS0103", "at Microsoft.Dafny.Translator.TrForall_NewValueAssumption(IToken tok, List\`1 boundVars, List\`1 bounds, Expression range, Expression lhs, Expression rhs, Attributes attributes, ExpressionTranslator etran, ExpressionTranslator prevEtran)"]
        return []

    def get_known_execution_errors(self) -> List[str]:
        if self is DafnyBackend.JAVA:
            return ["CodePoint"]

        return []

    # Usage: copy Dafny files to the corresponding regular / traced temporary folder.
    # Note: tracing output does not change the semantics of the program, it only creates additional artifact.
    # Hence we pool the behaviour in the same method
    def regular_compile_to_backend(self,
                                   dafny_binary: Path,
                                   dafny_file_dir: Path,
                                   dafny_file_name: str,  # no extensions
                                   timeout_in_seconds: int | float,
                                   trace_output_path: Optional[Path] = None) -> RegularDafnyCompileResult:
        if not self.is_supported:
            raise NotImplementedError()
        # Compiles the program with the Dafny compiler and produces artifacts that can be executed by the downstream
        # programming language.

        # All artifacts are within dafny_file_dir. This allows for convenient deletion.
        compile_command = ["dotnet", str(dafny_binary), "build", "--no-verify", "--allow-warnings",
                           f"--target:{self.target_flag}", f"{str(dafny_file_dir / dafny_file_name)}.dfy"]

        logger.info("Compiling with regular Dafny | Command: {command}", command=' '.join(compile_command))

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

        standard_output = stdout.decode('utf-8')

        logger.info(standard_output)
        if stderr:
            logger.error(stderr.decode('utf-8'))

        if exit_code != 0:
            program_status = RegularProgramStatus.COMPILER_ERROR

            if any(standard_output.contains(known_error_substring) for known_error_substring
                   in self.get_known_compilation_errors()):
                program_status = RegularProgramStatus.KNOWN_BUG

            logger.info("[DETECT] Exit code non-zero for regular compilation")
        elif timeout:
            program_status = RegularProgramStatus.COMPILER_ERROR
            logger.info("[DETECT] Timeout for regular compilation")
        else:
            program_status = RegularProgramStatus.EXPECTED_SUCCESS

        return RegularDafnyCompileResult(program_status=program_status, elapsed_time=elapsed_time)

    def regular_execution(self,
                          backend_artifact_dir: Path,
                          dafny_file_name: str,  # no extensions
                          timeout_in_seconds: int | float) -> RegularDafnyBackendExecutionResult:
        # Executes the binary resulting from Dafny compilation.
        execute_binary_command = self.get_execute_command(artifact_dir=backend_artifact_dir, file_name=dafny_file_name)

        logger.info("Executing regular Dafny compilation result | Command: {command}", command=' '.join(execute_binary_command))

        start_time = time.time()
        runtime_result = run_subprocess(execute_binary_command,
                                        timeout_in_seconds)  # (exit_code, stdout, stderr, timeout)
        elapsed_time = time.time() - start_time

        standard_output = runtime_result.stdout.decode('utf-8')

        logger.info(standard_output)
        if runtime_result.stderr:
            logger.error(runtime_result.stderr.decode('utf-8'))

        if runtime_result.timeout:
            program_status = RegularProgramStatus.RUNTIME_TIMEOUT
            logger.info("[DETECT] Timeout for regular execution")
        elif runtime_result.exit_code != 0:
            program_status = RegularProgramStatus.RUNTIME_EXITCODE_NON_ZERO

            if any(standard_output.contains(known_error_substring) for known_error_substring
                   in self.get_known_execution_errors()):
                program_status = RegularProgramStatus.KNOWN_BUG

            logger.info("[DETECT] Exit code non-zero for regular execution")
        else:
            program_status = RegularProgramStatus.EXPECTED_SUCCESS

        return RegularDafnyBackendExecutionResult(program_status=program_status,
                                                  execution_result=runtime_result,
                                                  elapsed_time=elapsed_time)

    def mutated_compile_to_backend(self,
                                   dafny_binary: Path,
                                   dafny_file_dir: Path,
                                   dafny_file_name: str,  # no extensions
                                   mutant_env_var: str,
                                   mutant_id: str,
                                   timeout_in_seconds: int | float) -> MutatedDafnyCompileResult:
        if not self.is_supported:
            raise NotImplementedError()
        # Compiles the program with the mutated Dafny compiler and produces artifacts that can be executed by the
        # downstream programming language.
        compile_command = ["dotnet", str(dafny_binary), "build", "--no-verify", "--allow-warnings",
                           f"--target:{self.target_flag}", f"{str(dafny_file_dir / dafny_file_name)}.dfy"]

        logger.info("Compiling with mutated Dafny | Command: {command}", command=' '.join(compile_command))

        # Prepare environment variable to instrument mutation.
        env_dict = os.environ.copy()
        env_dict[mutant_env_var] = mutant_id
        (exit_code, stdout, stderr, timeout) = run_subprocess(compile_command, timeout_in_seconds, env=env_dict)

        standard_output = stdout.decode('utf-8')
        logger.info(standard_output)
        if stderr:
            logger.error(stderr.decode('utf-8'))

        if timeout:
            print("[DETECT] Timeout for mutant compilation")
            mutant_status = MutantStatus.KILLED_COMPILER_TIMEOUT
        elif exit_code != 0:
            print("[DETECT] Crash for mutant compilation")
            mutant_status = MutantStatus.KILLED_COMPILER_CRASHED
        else:
            mutant_status = MutantStatus.SURVIVED

        return MutatedDafnyCompileResult(mutant_status)

    def mutant_execution(self,
                         dafny_file_dir: Path,
                         dafny_file_name: str,
                         default_execution_result: ProcessExecutionResult,
                         timeout_in_seconds: int | float) -> MutatedDafnyBackendExecutionResult:
        # Executes the binary resulting from Dafny compilation.
        execute_binary_command = self.get_execute_command(artifact_dir=dafny_file_dir, file_name=dafny_file_name)

        logger.info("Executing mutated Dafny compilation result | Command: {command}", command=' '.join(execute_binary_command))

        runtime_result = run_subprocess(execute_binary_command,
                                        timeout_in_seconds)  # (exit_code, stdout, stderr, timeout)

        logger.info(runtime_result.stdout.decode('utf-8'))
        if runtime_result.stderr:
            logger.error(runtime_result.stderr.decode('utf-8'))

        if runtime_result.timeout:
            print("[DETECT] Timeout for mutant execution")
            mutant_status = MutantStatus.KILLED_RUNTIME_TIMEOUT
        elif runtime_result.exit_code != default_execution_result.exit_code:
            print("[DETECT] Mutant Exit code differed from regular exit code")
            mutant_status = MutantStatus.KILLED_RUNTIME_EXITCODE_DIFFER
        elif runtime_result.stdout != default_execution_result.stdout:
            print("[DETECT] Mutant stdout differed from regular stdout")
            mutant_status = MutantStatus.KILLED_RUNTIME_STDOUT_DIFFER
        elif runtime_result.stderr != default_execution_result.stderr:
            print("[DETECT] Mutant stderr differed from regular stderr")
            mutant_status = MutantStatus.KILLED_RUNTIME_STDERR_DIFFER
        else:
            mutant_status = MutantStatus.SURVIVED

        return MutatedDafnyBackendExecutionResult(mutant_status=mutant_status)
