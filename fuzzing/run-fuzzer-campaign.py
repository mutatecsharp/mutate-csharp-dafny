#! /usr/bin/env python3.11
import dataclasses
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
from datetime import timedelta
from typing import List

from fuzzing.dafny import DafnyBackend
from fuzzing.util.file_hash import compute_file_hash
from fuzzing.util.mutant_status import MutantStatus
from fuzzing.util.mutation_registry import MutationRegistry
from fuzzing.util.mutation_test_result import MutationTestResult, MutationTestStatus
from fuzzing.util.instrument_type import InstrumentType
from fuzzing.util.run_subprocess import run_subprocess, ProcessExecutionResult

LONG_UPPER_BOUND = (1 << 64) - 1
COMPILATION_TIMEOUT_SCALE_FACTOR = 3
EXECUTION_TIMEOUT_SCALE_FACTOR = 3
EXECUTION_TRACE_OUTPUT_ENV_VAR = "MUTATE_CSHARP_TRACER_FILEPATH"


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


def validated_mutant_registry(mutation_registry_path: Path, tracer_registry_path: Path):
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

    elapsed_timedelta = timedelta(seconds=elapsed_time_in_seconds)
    print(f"Test campaign elapsed time: {str(elapsed_timedelta)}")

    return elapsed_time_in_seconds < time_budget_in_seconds


def execute_fuzz_d(java_binary: Path,
                   fuzz_d_binary: Path,
                   output_directory: Path,
                   seed: int,
                   timeout_in_seconds: int) -> bool:
    # Generates a randomised Dafny program.
    # (artifacts: fuzz-d.log, generated.dfy, (if passing) interpret_out.txt, (if passing) main.dfy)
    fuzz_command = [str(java_binary), "-jar", str(fuzz_d_binary), "fuzz", "--seed", str(seed), "--noRun", "--output",
                    str(output_directory)]
    (exit_code, _, _, timeout) = run_subprocess(fuzz_command, timeout_in_seconds)

    if timeout:
        print(f"Skipping: fuzz-d timeout (seed {seed}).")

    generated_file_exists = (output_directory / "main.dfy").exists()

    if not generated_file_exists:
        print("Skipping: fuzz-d failed to generate main.dfy.")

    return not timeout and exit_code == 0 and generated_file_exists


def execute_mutated_compiled_program(compiled_program_binary: Path,
                                     default_program_binary: Path,
                                     default_execution_result: ProcessExecutionResult,
                                     timeout_in_seconds: int) -> MutantStatus:
    # Optimisation: skip execution if file hash is equivalent
    default_file_hash = compute_file_hash(default_program_binary)
    mutated_file_hash = compute_file_hash(compiled_program_binary)
    if default_file_hash == mutated_file_hash:
        return MutantStatus.SURVIVED_HASH_EQUIVALENT

    # Executes the binary resulting from Dafny compilation.
    execute_binary_command = [str(compiled_program_binary)]
    (exit_code, stdout, stderr, timeout) = run_subprocess(execute_binary_command, timeout_in_seconds)

    if timeout:
        return MutantStatus.KILLED_COMPILER_TIMEOUT

    if exit_code != default_execution_result.exit_code:
        return MutantStatus.KILLED_RUNTIME_EXITCODE_DIFFER

    if stdout != default_execution_result.stdout:
        return MutantStatus.KILLED_RUNTIME_STDERR_DIFFER

    if stderr != default_execution_result.stderr:
        return MutantStatus.KILLED_RUNTIME_STDOUT_DIFFER

    return MutantStatus.SURVIVED_HASH_DIFFER


def mutation_guided_test_generation(fuzz_d_reliant_java_binary: Path,  # Java 19
                                    fuzz_d_binary: Path,
                                    default_dafny_binary: Path,
                                    mutated_dafny_binary: Path,
                                    traced_dafny_binary: Path,
                                    target_backends: List[DafnyBackend],
                                    compilation_artifact_dir: Path,
                                    tests_artifact_dir: Path,
                                    killed_mutants_artifact_dir: Path,
                                    regular_compilation_error_dir: Path,
                                    regular_wrong_code_dir: Path,
                                    mutation_test_results: MutationTestResult,
                                    source_file_env_var: Path | None,
                                    test_campaign_budget_in_hours: int,
                                    generation_budget_in_seconds: int,
                                    compilation_timeout_in_seconds: int,
                                    execution_timeout_in_seconds: int):
    # Mutation testing
    killed_mutants: set = set()  # set of (file_env_var, mutant_id)
    # Interesting mutants to generate tests against:
    # 1) Mutants that are not covered by any tests
    # 2) Mutants that are covered by at least one test but survive / passes all tests when activated
    uncovered_by_regression_tests_mutants = \
        [tuple(mutant.split(':')) for mutant in
         mutation_test_results.get_mutants_of_status(MutationTestStatus.Uncovered)]
    covered_by_regression_tests_but_survived_mutants = \
        [tuple(mutant.split(':')) for mutant in
         mutation_test_results.get_mutants_of_status(MutationTestStatus.Survived)]

    # Sanity checks: all input should conform to the expected behaviour
    if not all(len(mutant_info) == 2 for mutant_info in uncovered_by_regression_tests_mutants) or \
            not all(len(mutant_info) == 2 for mutant_info in covered_by_regression_tests_but_survived_mutants):
        print("Corrupted mutation testing results found.")
        exit(1)

    # set of (file_env_var, mutant_id)
    surviving_mutants: set = set(uncovered_by_regression_tests_mutants +
                                 covered_by_regression_tests_but_survived_mutants)

    time_of_last_kill = time.time()  # in seconds since epoch
    test_campaign_start_time = time.time()  # in seconds since epoch

    with (tempfile.TemporaryDirectory(dir=str(compilation_artifact_dir)) as temp_dir):
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
        fuzz_d_output_path = fuzz_d_generation_dir / 'main.dfy'
        default_compiled_executable_path = default_compilation_dir / 'default'
        mutated_compiled_executable_path = mutated_compilation_dir / 'mutated'
        traced_compiled_executable_path = traced_compilation_dir / 'traced'
        mutant_trace_file_path = execution_trace_output_dir / 'mutant-trace'

        while time_budget_exists(
                test_campaign_start_time_in_seconds=test_campaign_start_time,
                test_campaign_budget_in_hours=test_campaign_budget_in_hours) and len(surviving_mutants) > 0:
            fuzz_d_fuzzer_seed = random.randint(0, LONG_UPPER_BOUND)
            program_uid = f"fuzzd_{fuzz_d_fuzzer_seed}"  # note: seed can be negative?
            current_program_output_dir = tests_artifact_dir / program_uid

            # Sanity check: skip if another runner is working on the same seed
            if current_program_output_dir.exists():
                print(f"Skipping: another runner is working on the same seed ({fuzz_d_fuzzer_seed}).")
                continue

            # 0) Delete generated files from previous iteration.
            if fuzz_d_output_path.exists():
                fuzz_d_output_path.unlink()
            if mutant_trace_file_path.exists():
                mutant_trace_file_path.unlink()
            if default_compiled_executable_path.exists():
                default_compiled_executable_path.unlink()
            if mutated_compiled_executable_path.exists():
                mutated_compiled_executable_path.unlink()
            if traced_compiled_executable_path.exists():
                traced_compiled_executable_path.unlink()

            # 1) Generate a valid Dafny program
            if not execute_fuzz_d(fuzz_d_reliant_java_binary,
                                  fuzz_d_binary,
                                  fuzz_d_generation_dir,
                                  fuzz_d_fuzzer_seed,
                                  generation_budget_in_seconds):
                continue

            # 2) Compile the generated Dafny program with the default Dafny compiler to selected target backends
            regular_compilation_results = [
                (target,
                target.regular_compile_to_backend(dafny_binary=default_dafny_binary,
                                                  dafny_file_path=fuzz_d_output_path,
                                                  artifact_output_dir=default_compiled_executable_path,
                                                  artifact_name=f"regular-dafny-{target.name}",
                                                  timeout_in_seconds=compilation_timeout_in_seconds))
                for target in target_backends
            ]

            # 3) Differential testing: compilation of regular Dafny
            if any(not result.success for _, result in regular_compilation_results):
                # Copy fuzz-d generated program and Dafny compilation artifacts
                with tempfile.TemporaryDirectory(dir=str(regular_compilation_error_dir),
                                                 delete=False) as program_comp_error_dir:
                    print(f"Found compilation errors during compilation of fuzz-d generated program with the *regular* "
                          f"Dafny compiler. Results will be persisted to {program_comp_error_dir}.")
                    shutil.copytree(src=str(fuzz_d_generation_dir), dst=f"{program_comp_error_dir}/fuzz_d_generation")
                    shutil.copytree(src=str(default_compiled_executable_path),
                                    dst=f"{program_comp_error_dir}/default_compilation")
                    with open(f"{program_comp_error_dir}/error.log", "w") as error_io:
                        json.dump(
                            dict(
                            compilation_error=[dataclasses.asdict(result) for _, result in regular_compilation_results]),
                            error_io,
                            indent=4
                        )

                continue

            # 3) Execute the generated Dafny program with the executable artifact produced by the default Dafny compiler.
           regular_execution_results = [
                target.regular_execution(translated_src_path=results.)
                for target, results in regular_compilation_results
            ]

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

            # 5) Create directory for the generated program, using seed number to deduplicate efforts.
            try:
                current_program_output_dir.mkdir()
            except FileExistsError:
                print(f"Skipping: another runner is working on the same seed ({fuzz_d_fuzzer_seed}).")
                continue

            shutil.copyfile(src=fuzz_d_output_path, dst=current_mutation_testing_program_path)

            # 6) Load execution trace from disk.
            with open(mutant_trace_file_path, 'r') as mutant_trace_io:
                # remove duplicates
                mutants_covered_by_program = list(set([tuple(line.strip().split(':'))
                                                       for line in mutant_trace_io.readlines()]))

            if not all(len(env_var_to_mutant_id) == 2 for env_var_to_mutant_id in mutants_covered_by_program):
                print(f"Skipping: execution trace is corrupted. (seed: {fuzz_d_fuzzer_seed}))")
                continue

            # 7) Filter for particular source file under test if specified and discard killed mutants from consideration.
            if source_file_env_var is not None:
                mutants_covered_by_program = [(env_var, mutant_id) for (env_var, mutant_id) in
                                              mutants_covered_by_program if env_var == source_file_env_var]
            candidate_mutants_for_program = [(env_var, mutant_id) for (env_var, mutant_id) in mutants_covered_by_program
                                             if (env_var, mutant_id) not in killed_mutants]

            print(
                f"Number of mutants covered by generated program with seed {fuzz_d_fuzzer_seed}: {len(mutants_covered_by_program)}")

            # Sort mutants: since mutants that are sequential in ID are likely to belong in the same mutation group,
            # killing one mutant in the mutation group might lead to kills in the other mutants in the same mutation
            # group.
            mutants_covered_by_program.sort()

            # 8) Perform mutation testing on the generated Dafny program with the mutated Dafny compiler.
            mutants_skipped_by_program = [(env_var, mutant_id) for (env_var, mutant_id) in mutants_covered_by_program
                                          if (env_var, mutant_id) in killed_mutants]
            mutants_killed_by_program = []
            mutants_covered_but_not_killed_by_program = []

            for env_var, mutant_id in candidate_mutants_for_program:
                if not time_budget_exists(test_campaign_start_time_in_seconds=test_campaign_start_time,
                                          test_campaign_budget_in_hours=test_campaign_budget_in_hours) or \
                        len(surviving_mutants) == 0:
                    break

                # Important to verify the corresponding check in C# has the same name.
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
                if kill_status == MutantStatus.SURVIVED_HASH_EQUIVALENT \
                        or kill_status == MutantStatus.SURVIVED_HASH_DIFFER:
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
                        json.dump({"mutant": f"{env_var}:{mutant_id}",
                                   "killed_by_test": program_uid,
                                   "kill_status": kill_status.name}, killed_file_io, indent=4)
                except FileExistsError:
                    print(f"Skipping: another runner determined this mutant ({env_var}:{mutant_id}) can be killed.")
                    continue

            # 13) Complete testing current program against all surviving mutants.
            all_mutants_considered_by_program = mutants_killed_by_program + \
                                                mutants_covered_but_not_killed_by_program + \
                                                mutants_skipped_by_program
            all_mutants_considered_by_program.sort()  # there should not be duplicated mutants
            early_termination = mutants_covered_by_program != all_mutants_considered_by_program

            # 12) Persist test campaign summary/metadata.
            mutants_killed_by_program.sort()
            mutants_skipped_by_program.sort()
            mutants_covered_but_not_killed_by_program.sort()

            persisted_mutants_killed_by_program = \
                [f"{env_var}:{mutant_id}" for env_var, mutant_id in mutants_killed_by_program]
            persisted_mutants_covered_but_not_killed_by_program = \
                [f"{env_var}:{mutant_id}" for env_var, mutant_id in mutants_covered_but_not_killed_by_program]
            persisted_mutants_skipped_by_program = \
                [f"{env_var}:{mutant_id}" for env_var, mutant_id in mutants_skipped_by_program]
            persisted_mutants_covered_by_program = \
                [f"{env_var}:{mutant_id}" for env_var, mutant_id in mutants_covered_by_program]

            persisted_summary = {"test_name": program_uid,
                                 "early_termination": early_termination,
                                 "killed_mutants": persisted_mutants_killed_by_program,
                                 "skipped_mutants": persisted_mutants_skipped_by_program,
                                 "survived_mutants": persisted_mutants_covered_but_not_killed_by_program,
                                 "covered_mutants": persisted_mutants_covered_by_program}

            with open(str(current_program_output_dir / "test-summary.json"), "w") as summary_file_io:
                json.dump(persisted_summary, summary_file_io, indent=4)

            # time budget should be running out here
            if early_termination \
                    and time_budget_exists(test_campaign_start_time_in_seconds=test_campaign_start_time,
                                           test_campaign_budget_in_hours=test_campaign_budget_in_hours) \
                    and len(surviving_mutants) > 0:
                print(f"Unexpected program internal state. Terminating...")
                exit(1)


def main():
    if not validate_volume_directory_exists():
        print('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)

    env = obtain_env_vars()

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action='store_true',
                        help="Perform dry run.")
    parser.add_argument('--seed', type=int,
                        help='Optional. Seed for random number generator.')
    parser.add_argument("--fuzz_d", type=str,
                        help='Path to the fuzz-d project.')
    parser.add_argument("--dafny", type=str,
                        help='Path to the non-mutated Dafny project.')
    parser.add_argument("--mutated_dafny", type=str,
                        help='Path to the mutated Dafny project.')
    parser.add_argument("--traced_dafny", type=str,
                        help='Path to the execution-trace instrumented Dafny project.')
    parser.add_argument("--output_directory", type=str, required=True,
                        help='Path to the persisted/temporary interesting programs output directory.')
    parser.add_argument('--mutation_registry', type=str,
                        help='Path to registry generated after mutating the Dafny codebase (.json).')
    parser.add_argument('--tracer_registry', type=str,
                        help='Path to registry generated after instrumenting the Dafny codebase to trace mutant executions (.json).')
    parser.add_argument('--mutation_test_result', type=str, required=True,
                        help="Path to mutation testing result of the Dafny regression test suite (.json).")
    parser.add_argument('--source_file_relative_path', type=str,
                        help="Optional. If specified, only consider mutants for the specified file.")
    parser.add_argument('--compilation_timeout', default=30,
                        help='Maximum second(s) allowed to compile generated program with the non-mutated Dafny compiler.')
    parser.add_argument('--generation_timeout', default=30,
                        help='Maximum second(s) allowed to generate program with fuzz-d.')
    parser.add_argument('--execution_timeout', default=30,
                        help='Maximum second(s) allowed to execute fuzz-d generated program compiled by the non-mutated Dafny compiler.')
    parser.add_argument('--test_campaign_timeout', default=12,
                        help='Test campaign time budget in hour(s).')

    # CLI arguments
    args = parser.parse_args()

    # Set defaults
    if args.fuzz_d is not None:
        fuzz_d_root = Path(args.fuzz_d).resolve()
    else:
        fuzz_d_root = Path(f"{os.getcwd()}/third_party/fuzz-d")

    # Build fuzz-d (execution of fuzz-d relies on Java version 19)
    java_binary_path = Path(env['JAVA_19_BINARY_PATH'])
    fuzz_d_binary_path = fuzz_d_root / "app" / "build" / "libs" / "app.jar"
    os.system(f"cd {fuzz_d_root} && ./gradlew build && cd -")

    # Regular dafny
    if args.dafny is not None:
        regular_dafny_dir = Path(args.dafny).resolve()
    else:
        regular_dafny_dir = Path(f"{env['REGULAR_DAFNY_ROOT']}")

    dafny_binary_path = regular_dafny_dir / "Binaries" / "Dafny.dll"

    # Mutated dafny
    if args.mutated_dafny is not None:
        mutated_dafny_dir = Path(args.mutated_dafny).resolve()
    else:
        mutated_dafny_dir = Path(f"{env['MUTATED_DAFNY_ROOT']}")

    mutated_dafny_binary_path = mutated_dafny_dir / "Binaries" / "Dafny.dll"

    # Tracer dafny
    if args.traced_dafny is not None:
        traced_dafny_dir = Path(args.traced_dafny).resolve()
    else:
        traced_dafny_dir = Path(f"{env['TRACED_DAFNY_ROOT']}")

    traced_dafny_binary_path = traced_dafny_dir / "Binaries" / "Dafny.dll"

    if args.mutation_registry is not None:
        mutation_registry_path = Path(args.mutation_registry).resolve()
    else:
        mutation_registry_path = Path(f"{env['MUTATED_DAFNY_ROOT']}") / "Source" / "DafnyCore" / "registry.mucs.json"

    if args.tracer_registry is not None:
        tracer_registry_path = Path(args.tracer_registry).resolve()
    else:
        tracer_registry_path = Path(
            f"{env['TRACED_DAFNY_ROOT']}") / "Source" / "DafnyCore" / "tracer-registry.mucs.json"

    mutation_registry: MutationRegistry = validated_mutant_registry(mutation_registry_path, tracer_registry_path)
    mutation_test_results: MutationTestResult = MutationTestResult.reconstruct_from_disk(args.mutation_test_result)

    source_file_env_var = None
    if args.source_file_relative_path is not None:
        to_find = [registry['EnvironmentVariable'] for path, registry in
                   mutation_registry.file_relative_path_to_registry.items()
                   if path == args.source_file_relative_path]
        if len(to_find) == 0:
            print("Cannot find the specified file in mutation registry.")
            exit(1)
        elif len(to_find) > 1:
            print(
                "Found more than one match for the specified file in mutation registry. Mutation registry may be corrupted.")
            exit(1)
        source_file_env_var = to_find[0]

    artifact_directory = Path(args.output_directory).absolute()

    if not fuzz_d_binary_path.is_file() or \
            not dafny_binary_path.is_file() or \
            not mutated_dafny_binary_path.is_file() or \
            not traced_dafny_binary_path.is_file():
        print("Invalid fuzz-d or dafny binary executable paths.")

    # Create output directory if it does not exist
    compilation_artifact_dir = artifact_directory / "compilations"

    tests_artifact_dir = artifact_directory / 'tests'
    regular_compilation_error_dir = artifact_directory / 'regular-compilation-errors'
    regular_wrong_code_dir = artifact_directory / 'regular-wrong-code'
    killed_mutants_artifact_dir = artifact_directory / 'killed_mutants'

    print(f"fuzz-d project root: {fuzz_d_root}")
    print(f"regular dafny project root: {regular_dafny_dir}")
    print(f"mutated dafny project root: {mutated_dafny_dir}")
    print(f"traced dafny project root: {traced_dafny_dir}")
    print(f"compilation artifact output directory: {compilation_artifact_dir}")
    print(f"mutation testing artifact output directory: {tests_artifact_dir}")
    print(f"killed mutants artifact output directory: {killed_mutants_artifact_dir}")
    print(f"regular compilation error output directory: {regular_compilation_error_dir}")
    print(f"regular wrong code bug output directory: {regular_wrong_code_dir}")

    if source_file_env_var is not None:
        print(f"Specified file: {args.source_file_relative_path} | Env var: {source_file_env_var}")

    if args.dry_run:
        print("Dry run complete.")
        exit(0)

    compilation_artifact_dir.mkdir(parents=True, exist_ok=True)
    tests_artifact_dir.mkdir(parents=True, exist_ok=True)
    killed_mutants_artifact_dir.mkdir(parents=True, exist_ok=True)
    regular_wrong_code_dir.mkdir(parents=True, exist_ok=True)
    regular_compilation_error_dir.mkdir(parents=True, exist_ok=True)

    if args.seed is not None:
        random.seed(args.seed)

    # Modify if necessary.
    targeted_backends = [DafnyBackend.GO,
                         DafnyBackend.PYTHON,
                         DafnyBackend.CSHARP,
                         DafnyBackend.JAVASCRIPT,
                         DafnyBackend.JAVA]

    mutation_guided_test_generation(fuzz_d_reliant_java_binary=java_binary_path,
                                    fuzz_d_binary=fuzz_d_binary_path,
                                    default_dafny_binary=dafny_binary_path,
                                    mutated_dafny_binary=mutated_dafny_binary_path,
                                    traced_dafny_binary=traced_dafny_binary_path,
                                    target_backends=targeted_backends,
                                    compilation_artifact_dir=compilation_artifact_dir,
                                    tests_artifact_dir=tests_artifact_dir,
                                    killed_mutants_artifact_dir=killed_mutants_artifact_dir,
                                    regular_compilation_error_dir=regular_compilation_error_dir,
                                    regular_wrong_code_dir=regular_wrong_code_dir,
                                    mutation_test_results=mutation_test_results,
                                    source_file_env_var=source_file_env_var,
                                    test_campaign_budget_in_hours=args.test_campaign_timeout,
                                    generation_budget_in_seconds=args.generation_timeout,
                                    compilation_timeout_in_seconds=args.compilation_timeout,
                                    execution_timeout_in_seconds=args.execution_timeout)


if __name__ == '__main__':
    main()
