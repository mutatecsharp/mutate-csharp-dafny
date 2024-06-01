#! /usr/bin/env python3.11
import json
import os
import time
import random
import shlex
import shutil
import tempfile
import argparse
import subprocess

from pathlib import Path
from random import random
from enum import Enum
from datetime import timedelta

from fuzzing.util.file_hash import compute_file_hash
from fuzzing.util.mutation_registry import MutationRegistry
from fuzzing.util.instrument_type import InstrumentType
from fuzzing.util.run_subprocess import run_subprocess, ProcessExecutionResult

LONG_UPPER_BOUND = (1 << 64) - 1
COMPILATION_TIMEOUT_SCALE_FACTOR = 3
EXECUTION_TIMEOUT_SCALE_FACTOR = 3
EXECUTION_TRACE_OUTPUT_ENV_VAR = "MUTATE_CSHARP_TRACER_FILEPATH"


class KillStatus(Enum):
    KILLED_COMPILER_CRASHED = 1
    KILLED_COMPILER_TIMEOUT = 2
    KILLED_COMPILER_MISSING_EXECUTABLE_OUTPUT = 3
    KILLED_RUNTIME_TIMEOUT = 4
    KILLED_RUNTIME_EXITCODE_DIFFER = 5
    KILLED_RUNTIME_STDOUT_DIFFER = 6
    KILLED_RUNTIME_STDERR_DIFFER = 7
    SURVIVED_HASH_EQUIVALENT = 8
    SURVIVED_HASH_DIFFER = 9


def validate_volume_directory_exists():
    volume_dir = os.environ.get('VOLUME_ROOT')
    return volume_dir and os.path.exists(volume_dir)


def obtain_env_vars():
    # Sanity check: we should be in mutate-csharp-dafny directory
    if not os.path.exists('env.sh') or not os.path.exists('parallel.runsettings'):
        print('Please run this script from the root of the mutate-csharp-dafny directory.')
        exit(1)

    env_dict = {}

    # Source env.sh and print environment variables
    command = shlex.split("bash -c 'source env.sh && env'")
    proc = subprocess.Popen(command, stdout=subprocess.PIPE)
    for line in proc.stdout:
        decoded_line = line.decode('utf-8').strip()
        (key, _, value) = decoded_line.partition("=")
        env_dict[key] = value
    proc.communicate()

    return env_dict


def validated_mutant_registry(mutation_registry_path: str, tracer_registry_path: str):
    mutation_registry_path = Path(mutation_registry_path)
    tracer_registry_path = Path(tracer_registry_path)

    if mutation_registry_path.name != "registry.mucs.json" or tracer_registry_path.name != "tracer-registry.mucs.json":
        print("Invalid mutation/tracer registry path.")
        exit(1)

    mutation_registry = MutationRegistry.reconstruct_from_disk(mutation_registry_path)
    tracer_registry = MutationRegistry.reconstruct_from_disk(tracer_registry_path)
    print(f"Mutations found: {len(mutation_registry.file_relative_path_to_registry)}")

    # Sanity checks
    assert len(mutation_registry.file_relative_path_to_registry) == len(tracer_registry.file_relative_path_to_registry)
    assert mutation_registry.file_relative_path_to_registry == tracer_registry.file_relative_path_to_registry

    return mutation_registry


def time_budget_exists(test_campaign_start_time_in_seconds: float,
                       test_campaign_budget_in_hours: int):
    time_budget_in_seconds = test_campaign_budget_in_hours * 3600
    elapsed_time_in_seconds = int(time.time() - test_campaign_start_time_in_seconds)
    return elapsed_time_in_seconds < time_budget_in_seconds


def execute_fuzz_d(fuzz_d_binary: Path,
                   output_directory: Path,
                   seed: int,
                   timeout_in_seconds: int) -> bool:
    # Generates a randomised Dafny program.
    fuzz_command = [str(fuzz_d_binary), "fuzz", "--seed", str(seed), "--noRun", "--output", str(output_directory)]
    (exit_code, _, _, timeout) = run_subprocess(fuzz_command, timeout_in_seconds)

    if timeout:
        print(f"Skipping: fuzz-d timeout (seed {seed}).")

    return not timeout and exit_code == 0


def execute_dafny(dafny_binary: Path,
                  dafny_file_path: Path,
                  executable_output_path: Path,
                  dafny_type: InstrumentType,
                  timeout_in_seconds: int) -> (bool, float):
    # Compiles the program with the Dafny compiler and produces an executable artifact.
    compile_command = [str(dafny_binary), "build", "--no-verify", "--output", str(executable_output_path),
                       str(dafny_file_path)]

    start_time = time.time()
    (exit_code, stdout, stderr, timeout) = run_subprocess(compile_command, timeout_in_seconds)
    elapsed_time = time.time() - start_time

    # todo: convert stdout/stderr to string instead of bytes
    if exit_code != 0:
        print(f"""Skipping: error while compiling generated. ({dafny_type.name})
        Standard output:
        {stdout}
        Standard error:
        {stderr}
        """)
        return False, None

    if timeout:
        print(f"Skipping: timeout while compiling generated program. ({dafny_type.name})")
        return False, None

    if not executable_output_path.is_file():
        print(f"Skipping: executable from dafny compilation not found. ({dafny_type.name})")
        return False, None

    return True, elapsed_time


def execute_mutated_dafny(dafny_binary: Path,
                          dafny_file_path: Path,
                          mutant_env_var: str,
                          mutant_id: str,
                          executable_output_path: Path,
                          timeout_in_seconds: int) -> KillStatus | None:
    # Compiles the program with the Dafny compiler and produces an executable artifact.
    compile_command = [str(dafny_binary), "build", "--no-verify", "--output", str(executable_output_path),
                       str(dafny_file_path)]

    # Prepare environment variable to instrument mutation.
    env_dict = os.environ.copy()
    env_dict[mutant_env_var] = mutant_id

    (exit_code, stdout, stderr, timeout) = run_subprocess(compile_command, timeout_in_seconds, env=env_dict)

    if timeout:
        return KillStatus.KILLED_COMPILER_TIMEOUT
    if exit_code != 0:
        return KillStatus.KILLED_COMPILER_CRASHED
    if not executable_output_path.is_file():
        return KillStatus.KILLED_COMPILER_MISSING_EXECUTABLE_OUTPUT

    return None


def execute_compiled_program(compiled_program_binary: Path,
                             dafny_type: InstrumentType,
                             timeout_in_seconds: int) -> (ProcessExecutionResult, float):
    # Executes the binary resulting from Dafny compilation.
    execute_binary_command = [str(compiled_program_binary)]

    start_time = time.time()
    runtime_result = run_subprocess(execute_binary_command, timeout_in_seconds) # (exit_code, stdout, stderr, timeout)
    elapsed_time = time.time() - start_time

    if runtime_result.timeout:
        print(f"Skipping: timeout while running executable of generated program. ({dafny_type.name})")

    if runtime_result.exit_code != 0:
        print(f"Skipping: error while running executable of generated program. ({dafny_type.name})")

    return runtime_result, elapsed_time


def execute_mutated_compiled_program(compiled_program_binary: Path,
                                     default_program_binary: Path,
                                     default_execution_result: ProcessExecutionResult,
                                     timeout_in_seconds: int) -> KillStatus:
    # Optimisation: skip execution if file hash is equivalent
    default_file_hash = compute_file_hash(default_program_binary)
    mutated_file_hash = compute_file_hash(compiled_program_binary)
    if default_file_hash == mutated_file_hash:
        return KillStatus.SURVIVED_HASH_EQUIVALENT

    # Executes the binary resulting from Dafny compilation.
    execute_binary_command = [str(compiled_program_binary)]
    (exit_code, stdout, stderr, timeout) = run_subprocess(execute_binary_command, timeout_in_seconds)

    if timeout:
        return KillStatus.KILLED_COMPILER_TIMEOUT

    if exit_code != default_execution_result.exit_code:
        return KillStatus.KILLED_RUNTIME_EXITCODE_DIFFER

    if stdout != default_execution_result.stdout:
        return KillStatus.KILLED_RUNTIME_STDERR_DIFFER

    if stderr != default_execution_result.stderr:
        return KillStatus.KILLED_RUNTIME_STDOUT_DIFFER

    return KillStatus.SURVIVED_HASH_DIFFER


def mutation_guided_test_generation(fuzz_d_binary: Path,
                                    default_dafny_binary: Path,
                                    mutated_dafny_binary: Path,
                                    traced_dafny_binary: Path,
                                    compilation_artifact_dir: Path,
                                    mutation_testing_artifact_dir: Path,
                                    killed_mutants_artifact_dir: Path,
                                    mutation_registry: MutationRegistry,
                                    source_file_under_test_relative_path: Path,
                                    test_campaign_budget_in_hours: int,
                                    generation_budget_in_seconds: int,
                                    compilation_timeout_in_seconds: int,
                                    execution_timeout_in_seconds: int):
    # Mutation testing
    killed_mutants: set = set()  # set of (file_env_var, mutant_id)
    surviving_mutants: set = set()  # todo: update with candidates

    time_of_last_kill = time.time()  # in seconds since epoch
    test_campaign_start_time = time.time()  # in seconds since epoch

    with tempfile.TemporaryDirectory(dir=str(compilation_artifact_dir)) as temp_dir:
        print(f"Temporary directory created at: {temp_dir}")

        # Initialise temporary directories
        fuzz_d_generation_dir = Path(temp_dir) / 'fuzz_d_generation'
        execution_trace_output_dir = Path(temp_dir) / 'execution_trace_output'
        mutated_compilation_dir = Path(temp_dir) / 'mutated_compilation'
        traced_compilation_dir = Path(temp_dir) / 'traced_compilation'
        default_compilation_dir = Path(temp_dir) / 'default_compilation'

        fuzz_d_generation_dir.mkdir()
        execution_trace_output_dir.mkdir()
        mutated_compilation_dir.mkdir()
        traced_compilation_dir.mkdir()
        default_compilation_dir.mkdir()

        # Initialise expected path
        fuzz_d_output_path = fuzz_d_generation_dir / 'generated.dfy'
        default_compiled_executable_path = default_compilation_dir / 'default'
        mutated_compiled_executable_path = mutated_compilation_dir / 'mutated'
        traced_compiled_executable_path = traced_compilation_dir / 'traced'
        mutant_trace_file_path = execution_trace_output_dir / 'mutant-trace'

        while time_budget_exists(
                test_campaign_start_time_in_seconds=test_campaign_start_time,
                test_campaign_budget_in_hours=test_campaign_budget_in_hours) and len(surviving_mutants) > 0:
            fuzz_d_fuzzer_seed = random.randint(0, LONG_UPPER_BOUND)
            program_uid = f"fuzzd-{fuzz_d_fuzzer_seed}"
            current_mutation_testing_dir = mutation_testing_artifact_dir / program_uid
            current_mutation_testing_program_path = current_mutation_testing_dir / 'valid.dfy'

            # Sanity check: skip if another runner is working on the same seed
            if current_mutation_testing_dir.exists():
                print(f"Skipping: another runner is working on the same seed ({fuzz_d_fuzzer_seed}).")
                continue

            # todo: delete compilations
            # 1) Generate a valid Dafny program
            if not execute_fuzz_d(fuzz_d_binary,
                                  fuzz_d_generation_dir,
                                  fuzz_d_fuzzer_seed,
                                  generation_budget_in_seconds):
                continue

            if not fuzz_d_output_path.is_file():
                print("Skipping: fuzz-d generated program not found. Check if setup is correct.")
                continue

            # 2) Compile the generated Dafny program with the default Dafny compiler
            default_compile_success, compile_elapsed_time = \
                execute_dafny(dafny_binary=default_dafny_binary,
                              dafny_file_path=fuzz_d_output_path,
                              executable_output_path=default_compiled_executable_path,
                              dafny_type=InstrumentType.DEFAULT,
                              timeout_in_seconds=compilation_timeout_in_seconds)
            if not default_compile_success:
                continue

            # 3) Execute the generated Dafny program with the executable artifact produced by the default Dafny compiler.
            default_execution_result, execution_elapsed_time = \
                execute_compiled_program(compiled_program_binary=default_compiled_executable_path,
                                         dafny_type=InstrumentType.DEFAULT,
                                         timeout_in_seconds=execution_timeout_in_seconds)
            if default_execution_result.timeout or default_execution_result.exit_code != 0:
                continue

            # 4) Compile the generated Dafny program with the trace-instrumented Dafny compiler.
            env_dict = os.environ.copy()
            env_dict[EXECUTION_TRACE_OUTPUT_ENV_VAR] = str(mutant_trace_file_path)
            traced_compile_success, _ = \
                execute_dafny(dafny_binary=traced_dafny_binary,
                              dafny_file_path=fuzz_d_output_path,
                              executable_output_path=traced_compiled_executable_path,
                              dafny_type=InstrumentType.TRACED,
                              timeout_in_seconds=compilation_timeout_in_seconds)
            if not traced_compile_success:
                continue
            if not mutant_trace_file_path.exists():
                print("Skipping: either the generated program execution trace does not cover any mutants, "
                      "or injection of trace output path environment variable failed. If this persists, check if the "
                      "injection performs as expected.")
                continue

            # 5) Create directory to perform mutation testing, using seed number to deduplicate efforts.
            try:
                current_mutation_testing_dir.mkdir()
            except FileExistsError:
                print(f"Skipping: another runner is working on the same seed ({fuzz_d_fuzzer_seed}).")
                continue

            shutil.copyfile(src=fuzz_d_output_path, dst=current_mutation_testing_program_path)

            # 6) Load execution trace from disk.
            with open(mutant_trace_file_path, 'r') as mutant_trace_io:
                mutants_covered_by_program = list(set([tuple(line.strip().split(':'))
                                                       for line in mutant_trace_io.readlines()]))

            if not all(len(env_var_to_mutant_id) == 2 for env_var_to_mutant_id in mutants_covered_by_program):
                print(f"Skipping: execution trace is corrupted. (seed: {fuzz_d_fuzzer_seed}))")
                continue

            # todo: get env var for particular source file under test
            # 7) Filter for particular source file under test if specified and discard killed mutants from consideration.
            source_file_under_test_env_var = None
            if source_file_under_test_env_var is not None:
                mutants_covered_by_program = [(env_var, mutant_id) for (env_var, mutant_id) in
                                              mutants_covered_by_program if env_var == source_file_under_test_env_var]
            mutants_covered_by_program = [(env_var, mutant_id) for (env_var, mutant_id) in mutants_covered_by_program
                                          if (env_var, mutant_id) not in killed_mutants]

            print(
                f"Number of mutants covered by generated program with seed {fuzz_d_fuzzer_seed}: {len(mutants_covered_by_program)}")

            # Sort mutants: since mutants that are sequential in ID are likely to belong in the same mutation group,
            # killing one mutant in the mutation group might lead to kills in the other mutants in the same mutation group.
            mutants_covered_by_program.sort()

            # 8) Perform mutation testing on the generated Dafny program with the mutated Dafny compiler.
            mutants_skipped_by_program = []
            mutants_killed_by_program = []
            mutants_covered_but_not_killed_by_program = []

            for env_var, mutant_id in mutants_covered_by_program:
                if not time_budget_exists(test_campaign_start_time_in_seconds=test_campaign_start_time,
                                          test_campaign_budget_in_hours=test_campaign_budget_in_hours) or \
                        len(surviving_mutants) == 0:
                    break

                mutant_killed_dir = killed_mutants_artifact_dir / f"{env_var}-{mutant_id}"
                if mutant_killed_dir.exists():
                    surviving_mutants.remove((env_var, mutant_id))
                    killed_mutants.add((env_var, mutant_id))
                    mutants_skipped_by_program.append((env_var, mutant_id))
                    print(f"Skipping: mutant {env_var}:{mutant_id} was killed by another runner.")

                print(f"Surviving mutants: {len(surviving_mutants)} | Killed mutants: {len(killed_mutants)}")
                print(f"Processing mutant {env_var}:{mutant_id} with program generated by seed {fuzz_d_fuzzer_seed}.")

                try:
                    if mutated_compiled_executable_path.is_file():
                        mutated_compiled_executable_path.unlink()
                except PermissionError:
                    print(f"Permission denied: cannot delete mutated binary at {str(mutated_compiled_executable_path)}")

                # 9) Compile the generated Dafny program with the mutation-instrumented Dafny compiler.
                maybe_kill_status = \
                    execute_mutated_dafny(dafny_binary=mutated_dafny_binary,
                                          dafny_file_path=fuzz_d_output_path,
                                          mutant_env_var=env_var,
                                          mutant_id=mutant_id,
                                          executable_output_path=mutated_compiled_executable_path,
                                          timeout_in_seconds=max(compilation_timeout_in_seconds,
                                                                 compile_elapsed_time *
                                                                 COMPILATION_TIMEOUT_SCALE_FACTOR))

                if maybe_kill_status is not None:
                    kill_status = maybe_kill_status  # found a bug during compilation time
                else:
                    # try to find a bug during execution time
                    # 10) Execute the generated Dafny program with the executable artifact produced by mutated Dafny compiler.
                    kill_status = \
                        execute_mutated_compiled_program(compiled_program_binary=mutated_compiled_executable_path,
                                                         default_program_binary=default_compiled_executable_path,
                                                         default_execution_result=default_execution_result,
                                                         timeout_in_seconds=max(execution_timeout_in_seconds,
                                                                                execution_elapsed_time *
                                                                                EXECUTION_TIMEOUT_SCALE_FACTOR))

                print(f"Finished processing mutant {env_var}:{mutant_id}. Kill result: {kill_status.name}")
                if kill_status == KillStatus.SURVIVED_HASH_EQUIVALENT or kill_status == KillStatus.SURVIVED_HASH_DIFFER:
                    mutants_covered_but_not_killed_by_program.append((env_var, mutant_id))
                    continue

                # 11) If we reached here, we found a test case to contribute to Dafny! Good work.
                surviving_mutants.remove((env_var, mutant_id))
                killed_mutants.add((env_var, mutant_id))
                mutants_killed_by_program.append((env_var, mutant_id))
                kill_elapsed_time = time.time() - time_of_last_kill
                time_of_last_kill = time.time()
                print(f"Killed mutants: {len(killed_mutants)} | Time taken since last kill: {str(kill_elapsed_time)}")

                try:
                    mutant_killed_dir.mkdir()
                    with open(str(mutant_killed_dir / "kill_info.json"), "w") as killed_file_io:
                        json.dump({"killed_by_test": program_uid, "kill_status": kill_status.name}, killed_file_io)
                except FileExistsError:
                    print(f"Skipping: another runner determined this mutant ({env_var}:{mutant_id}) can be killed.")
                    continue



def main():
    if not validate_volume_directory_exists():
        print('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)

    # todo: use defaults
    env = obtain_env_vars()

    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, help='Seed for random number generator.')
    parser.add_argument("--fuzz-d", type=str, required=True, help='Path to the fuzz-d binary.',
                        default=f"{os.getcwd()}/third_party/fuzz-d/app/build/libs/app.jar")
    parser.add_argument("--dafny", type=str, required=True, help='Path to the non-mutated Dafny binary.')
    parser.add_argument("--mutated-dafny", type=str, required=True, help='Path to the mutated Dafny binary.')
    parser.add_argument("--traced-dafny", type=str, required=True,
                        help='Path to the execution-trace instrumented Dafny binary.')
    parser.add_argument("--output-directory", type=str, required=True,
                        help='Path to the persisted/temporary interesting programs output directory.')
    parser.add_argument('--mutation-registry', type=str, required=True,
                        help='Path to registry generated after mutating the Dafny codebase.')
    parser.add_argument('--tracer-registry', type=str, required=True,
                        help='Path to registry generated after instrumenting the Dafny codebase to trace mutant executions.')
    parser.add_argument('--compilation-timeout', default=30,
                        help='Maximum second(s) allowed to compile generated program with the non-mutated Dafny compiler.')
    parser.add_argument('--generation-timeout', default=30,
                        help='Maximum second(s) allowed to generate program with fuzz-d.')
    parser.add_argument('--execution-timeout', default=30,
                        help='Maximum second(s) allowed to execute fuzz-d generated program compiled by the non-mutated Dafny compiler.')
    parser.add_argument('--test-campaign-timeout', default=12,
                        help='Test campaign time budget in hour(s).')

    # CLI arguments
    args = parser.parse_args()

    fuzz_d_binary_path = Path(args.fuzz_d).absolute()
    dafny_binary_path = Path(args.dafny).absolute()
    mutated_dafny_binary_path = Path(args.mutated_dafny).absolute()
    traced_dafny_binary_path = Path(args.traced_dafny).absolute()
    artifact_directory = Path(args.output_directory).absolute()

    if args.seed is not None:
        random.seed(args.seed)

    if not fuzz_d_binary_path.is_file() or \
            not dafny_binary_path.is_file() or \
            not mutated_dafny_binary_path.is_file() or \
            not traced_dafny_binary_path.is_file():
        print("Invalid fuzz-d or dafny binary executable paths.")

    mutation_registry: MutationRegistry = validated_mutant_registry(args.mutation_registry, args.tracer_registry)

    # Create output directory if it does not exist
    # artifact_directory.mkdir(parents=True, exist_ok=True)
    compilation_artifact_dir = artifact_directory / "compilations"
    mutation_testing_artifact_dir = artifact_directory / 'mutation_testing'
    killed_mutants_artifact_dir = artifact_directory / 'killed_mutants'
    compilation_artifact_dir.mkdir(parents=True, exist_ok=True)
    mutation_testing_artifact_dir.mkdir(parents=True, exist_ok=True)
    killed_mutants_artifact_dir.mkdir(parents=True, exist_ok=True)

    mutation_guided_test_generation(fuzz_d_binary=fuzz_d_binary_path,
                                    default_dafny_binary=dafny_binary_path,
                                    mutated_dafny_binary=mutated_dafny_binary_path,
                                    traced_dafny_binary=traced_dafny_binary_path,
                                    compilation_artifact_dir=compilation_artifact_dir,
                                    mutation_testing_artifact_dir=mutation_testing_artifact_dir,
                                    killed_mutants_artifact_dir=killed_mutants_artifact_dir,
                                    mutation_registry=mutation_registry,
                                    test_campaign_budget_in_hours=args.test_campaign_timeout,
                                    generation_budget_in_seconds=args.generation_timeout,
                                    default_compilation_timeout_in_seconds=args.compilation_timeout)


if __name__ == '__main__':
    main()
