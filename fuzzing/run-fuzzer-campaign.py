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
from datetime import timedelta
from typing import List, Dict, Set, Tuple
from itertools import chain
from loguru import logger

from dafny import DafnyBackend, RegularDafnyCompileResult, RegularDafnyBackendExecutionResult, \
    MutatedDafnyCompileResult, MutatedDafnyBackendExecutionResult
from util.program_status import MutantStatus, RegularProgramStatus
from util.mutation_registry import MutationRegistry
from util.mutation_test_result import MutationTestResult, MutationTestStatus
from util.mutant_trace import MutantTrace, RegressionTestsMutantTraces
from util.run_subprocess import run_subprocess, ProcessExecutionResult
from util.helper import all_equal, empty_directory
from util import constants, regression_tests

LONG_LOWER_BOUND = -(1 << 63)
LONG_UPPER_BOUND = (1 << 63) - 1
COMPILATION_TIMEOUT_SCALE_FACTOR = 3
EXECUTION_TIMEOUT_SCALE_FACTOR = 3
EXECUTION_TRACE_OUTPUT_ENV_VAR = "MUTATE_CSHARP_TRACER_FILEPATH"


def validate_volume_directory_exists():
    volume_dir = os.environ.get('VOLUME_ROOT')
    return volume_dir and os.path.exists(volume_dir)


def obtain_env_vars():
    # Sanity check: we should be in mutate-csharp-dafny directory
    if not os.path.exists('env.sh') or not os.path.exists('parallel.runsettings'):
        logger.error('Please run this script from the root of the mutate-csharp-dafny directory.')
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
        logger.error("Invalid mutation/tracer registry path.")
        exit(1)

    mutation_registry = MutationRegistry.reconstruct_from_disk(mutation_registry_path)
    tracer_registry = MutationRegistry.reconstruct_from_disk(tracer_registry_path)
    logger.info(f"Files mutated: {len(mutation_registry.file_relative_path_to_registry)}")

    # Sanity checks
    assert len(mutation_registry.file_relative_path_to_registry) == len(tracer_registry.file_relative_path_to_registry)
    assert set(mutation_registry.file_relative_path_to_registry.keys()) == set(
        tracer_registry.file_relative_path_to_registry.keys())
    assert set(mutation_registry.env_var_to_registry.keys()) == set(tracer_registry.env_var_to_registry.keys())
    for file_env_var in mutation_registry.env_var_to_registry.keys():
        assert len(mutation_registry.get_file_registry(file_env_var).mutations) == \
               len(tracer_registry.get_file_registry(file_env_var).mutations)
        for mutation in mutation_registry.get_file_registry(file_env_var).mutations.keys():
            assert mutation in tracer_registry.get_file_registry(file_env_var).mutations

    return mutation_registry


def time_budget_exists(test_campaign_start_time_in_seconds: float,
                       test_campaign_budget_in_hours: int):
    time_budget_in_seconds = test_campaign_budget_in_hours * 3600
    elapsed_time_in_seconds = int(time.time() - test_campaign_start_time_in_seconds)

    elapsed_timedelta = timedelta(seconds=elapsed_time_in_seconds)
    logger.info(f"Test campaign elapsed time: {str(elapsed_timedelta)}")

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

    logger.info("Generating Dafny program with fuzz-d | Command: {command}", command=' '.join(fuzz_command))

    (exit_code, stdout, stderr, timeout) = run_subprocess(fuzz_command, timeout_in_seconds)

    logger.info(stdout.decode('utf-8'))
    if stderr:
        logger.error(stderr.decode('utf-8'))

    if timeout:
        logger.warning(f"Skipping: fuzz-d timeout (seed {seed}).")

    generated_file_exists = (output_directory / f"{constants.FUZZ_D_GENERATED_FILENAME}.dfy").exists()

    if not generated_file_exists:
        logger.warning(f"Skipping: fuzz-d failed to generate {constants.FUZZ_D_GENERATED_FILENAME}.dfy.")

    return not timeout and exit_code == 0 and generated_file_exists


@logger.catch
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
                                    mutation_registry: MutationRegistry,
                                    mutation_test_results: MutationTestResult | None,
                                    regression_tests_mutant_traces: Dict[str, Set[Tuple[str, str]]] | None,
                                    source_file_env_var: Path | None,
                                    test_campaign_budget_in_hours: int,
                                    generation_budget_in_seconds: int,
                                    compilation_timeout_in_seconds: int,
                                    execution_timeout_in_seconds: int):
    # Mutation testing
    killed_mutants: set = set()  # set of (file_env_var, mutant_id)
    covered_by_regression_tests_but_survived_mutants = set()

    # Interesting mutants to generate tests against:
    # 1) Mutants that are not covered by any tests
    # 2) Mutants that are covered by at least one test but survive / passes all tests when activated
    if mutation_test_results is not None:
        uncovered_by_regression_tests_mutants = \
            set(tuple(mutant.split(':')) for mutant in
                mutation_test_results.get_mutants_of_status(MutationTestStatus.Uncovered))
        covered_by_regression_tests_but_survived_mutants = \
            set(tuple(mutant.split(':')) for mutant in
                mutation_test_results.get_mutants_of_status(MutationTestStatus.Survived))
    elif regression_tests_mutant_traces is not None:
        # Optimisation: if mutation testing results are not available for regression test suite, we consider all
        # covered mutants as killed and only fuzz to kill uncovered mutants. This allows both mutation testing
        # to be run in parallel to fuzzing once execution trace is collected.
        if source_file_env_var is not None:
            all_mutants = \
                set([(source_file_env_var, mutant_id) for mutant_id in
                     mutation_registry.get_file_registry(str(source_file_env_var)).mutations.keys()])
        else:
            # concat list of mutations with itertools.chain
            all_mutations = chain.from_iterable(
                registry.mutations for registry in mutation_registry.env_var_to_registry.values())
            all_mutants = set([(source_file_env_var, mutant_id) for mutant_id in all_mutations.keys()])
        assert len(all_mutants) > 0

        covered_by_regression_tests_mutants = set(chain.from_iterable(regression_tests_mutant_traces.values()))
        uncovered_by_regression_tests_mutants = all_mutants.difference(covered_by_regression_tests_mutants)
    else:
        logger.error("Insufficient information to fuzz.")
        exit(1)

    # Sanity checks: all input should conform to the expected behaviour
    if not all(len(mutant_info) == 2 for mutant_info in uncovered_by_regression_tests_mutants) or \
            not all(len(mutant_info) == 2 for mutant_info in covered_by_regression_tests_but_survived_mutants):
        logger.error("Corrupted mutation testing results found.")
        exit(1)

    # set of (file_env_var, mutant_id)
    surviving_mutants: set = set(uncovered_by_regression_tests_mutants.union(
        covered_by_regression_tests_but_survived_mutants))
    logger.info("Live mutants: {} | Mutants unreachable by Dafny regression tests: {}", len(surviving_mutants),
                len(uncovered_by_regression_tests_mutants))

    time_of_last_kill = time.time()  # in seconds since epoch
    test_campaign_start_time = time.time()  # in seconds since epoch
    iterations = 0
    valid_programs = 0

    with (tempfile.TemporaryDirectory(dir=str(compilation_artifact_dir)) as temp_dir):
        logger.info(f"Temporary directory created at: {temp_dir}")

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

        while time_budget_exists(
                test_campaign_start_time_in_seconds=test_campaign_start_time,
                test_campaign_budget_in_hours=test_campaign_budget_in_hours) and len(surviving_mutants) > 0:
            iterations += 1
            fuzz_d_fuzzer_seed = random.randint(LONG_LOWER_BOUND, LONG_UPPER_BOUND)
            program_uid = f"fuzzd_{fuzz_d_fuzzer_seed}"  # note: seed can be negative?
            current_program_output_dir = tests_artifact_dir / program_uid

            # Sanity check: skip if another runner is working on the same seed
            if current_program_output_dir.exists():
                logger.info(f"Skipping: another runner is working on the same seed ({fuzz_d_fuzzer_seed}).")
                continue

            # 0) Delete generated directories from previous iteration.
            empty_directory(fuzz_d_generation_dir)
            empty_directory(execution_trace_output_dir)
            empty_directory(mutated_compilation_dir)
            empty_directory(traced_compilation_dir)
            empty_directory(default_compilation_dir)

            # Sanity check: directory is empty.
            assert not any(fuzz_d_generation_dir.iterdir())
            assert not any(execution_trace_output_dir.iterdir())
            assert not any(mutated_compilation_dir.iterdir())
            assert not any(traced_compilation_dir.iterdir())
            assert not any(default_compilation_dir.iterdir())

            logger.info("Attempts: {} | Valid programs generated: {} | Live mutants: {} | Killed mutants: {} | "
                        "Total mutants considered: {}",
                        iterations,
                        valid_programs,
                        len(surviving_mutants),
                        len(killed_mutants),
                        len(surviving_mutants) + len(killed_mutants))
            logger.info("Fuzzing with fuzz-d with seed {}", fuzz_d_fuzzer_seed)

            # 1) Generate a valid Dafny program
            if not execute_fuzz_d(fuzz_d_reliant_java_binary,
                                  fuzz_d_binary,
                                  fuzz_d_generation_dir,
                                  fuzz_d_fuzzer_seed,
                                  generation_budget_in_seconds):
                continue

            logger.info("fuzz-d generated program can be found at: {}", fuzz_d_generation_dir)

            # 2) Copy the fuzz-d generated Dafny program to other mode directories.
            try:
                current_program_output_dir.mkdir()
            except FileExistsError:
                logger.info(f"Skipping: another runner is working on the same seed ({fuzz_d_fuzzer_seed}).")
                continue

            copy_destinations = [current_program_output_dir, mutated_compilation_dir, traced_compilation_dir,
                                 default_compilation_dir]

            for destination in copy_destinations:
                shutil.copytree(src=fuzz_d_generation_dir, dst=destination, dirs_exist_ok=True)

            # 3) Compile the generated Dafny program with the default Dafny compiler to selected target backends
            regular_compilation_results = {
                target:
                    target.regular_compile_to_backend(dafny_binary=default_dafny_binary,
                                                      dafny_file_dir=default_compilation_dir,
                                                      dafny_file_name=constants.FUZZ_D_GENERATED_FILENAME,
                                                      timeout_in_seconds=compilation_timeout_in_seconds)
                for target in target_backends
            }  # dict

            # Handle special case where error is known
            if any(result.program_status == RegularProgramStatus.KNOWN_BUG for result in
                   regular_compilation_results.values()):
                logger.info("Skipping: found known bug with program seeded by {}.", fuzz_d_fuzzer_seed)
                continue

            def persist_failed_program(overall_status_code: RegularProgramStatus, result_list: Dict[
                DafnyBackend, RegularDafnyCompileResult | RegularDafnyBackendExecutionResult], program_error_dir: Path):
                # Copy fuzz-d generated program and Dafny compilation artifacts
                try:
                    program_error_dir.mkdir()
                    logger.error(f"Error occurred with fuzz-d generated program and the *regular* "
                                 f"Dafny compiler. Results will be persisted to {program_error_dir}.")
                    shutil.copytree(src=str(fuzz_d_generation_dir),
                                    dst=f"{program_error_dir}/fuzz_d_generation")
                    shutil.copytree(src=str(default_compilation_dir),
                                    dst=f"{program_error_dir}/default_compilation")
                    with open(f"{program_error_dir}/regular_error.json", "w") as regular_error_file:
                        json.dump({"overall_status": overall_status_code.name,
                                   "failed_target_backends": [
                                       {"backend": backend.name, "program_status": result.program_status.name}
                                       for backend, result in result_list.items() if
                                       result.program_status != RegularProgramStatus.EXPECTED_SUCCESS]
                                   }, regular_error_file, indent=4)
                except FileExistsError:
                    logger.info(f"Program with seed {fuzz_d_fuzzer_seed} was independently found to identify "
                                f"faults in the Dafny compiler.")

            # 4) Differential testing: compilation of regular Dafny
            if any(result.program_status == RegularProgramStatus.COMPILER_ERROR for _, result in
                   regular_compilation_results.items()):
                persist_failed_program(RegularProgramStatus.COMPILER_ERROR, regular_compilation_results,
                                       regular_compilation_error_dir / program_uid)
                continue

            # 5) Execute the generated Dafny program with the executable artifact produced by the default Dafny compiler
            regular_execution_results = {
                target:
                    target.regular_execution(backend_artifact_dir=default_compilation_dir,
                                             dafny_file_name=constants.FUZZ_D_GENERATED_FILENAME,
                                             timeout_in_seconds=execution_timeout_in_seconds)
                for target, results in regular_compilation_results.items()
            }

            # Handle special case where error is known
            if any(result.program_status == RegularProgramStatus.KNOWN_BUG for result in
                   regular_execution_results.values()):
                logger.info("Skipping: found known bug with program seeded by {}.", fuzz_d_fuzzer_seed)
                continue

            # 6) Sanity check for non-zero runtime error code
            if any(result.program_status == RegularProgramStatus.RUNTIME_EXITCODE_NON_ZERO for result in
                   regular_execution_results.values()):
                persist_failed_program(RegularProgramStatus.RUNTIME_EXITCODE_NON_ZERO, regular_execution_results,
                                       regular_wrong_code_dir / program_uid)
                continue

            # 7) Differential testing: execution of regular Dafny
            if any(result.execution_result.timeout for target, result in regular_execution_results.items()):
                persist_failed_program(RegularProgramStatus.RUNTIME_TIMEOUT, regular_execution_results,
                                       regular_wrong_code_dir / program_uid)
                continue

            if not all_equal(result.execution_result.exit_code for result in regular_execution_results.values()):
                persist_failed_program(RegularProgramStatus.RUNTIME_EXITCODE_DIFFER, regular_execution_results,
                                       regular_wrong_code_dir / program_uid)
                continue

            if not all_equal(result.execution_result.stdout for result in regular_execution_results.values()):
                persist_failed_program(RegularProgramStatus.RUNTIME_STDOUT_DIFFER, regular_execution_results,
                                       regular_wrong_code_dir / program_uid)
                continue

            if not all_equal(result.execution_result.stderr for result in regular_execution_results.values()):
                persist_failed_program(RegularProgramStatus.RUNTIME_STDERR_DIFFER, regular_execution_results,
                                       regular_wrong_code_dir / program_uid)
                continue

            valid_programs += 1

            # 8) Compile the generated Dafny program with the trace-instrumented Dafny compiler.
            traced_compilation_results = [
                (target,
                 execution_trace_output_dir / f"mutant-trace-{target.name}",
                 target.regular_compile_to_backend(dafny_binary=traced_dafny_binary,
                                                   dafny_file_dir=traced_compilation_dir,
                                                   dafny_file_name=constants.FUZZ_D_GENERATED_FILENAME,
                                                   timeout_in_seconds=compilation_timeout_in_seconds,
                                                   trace_output_path=execution_trace_output_dir / f"mutant-trace-{target.name}"))
                for target in target_backends
            ]

            if all(not trace_path.exists() for _, trace_path, _ in traced_compilation_results):
                logger.info("No trace information found. This could be either the generated program "
                            "does not cover any mutants, or the tracer setup is invalid.")
                continue

            # 9) Create directory for the generated program, using seed number to deduplicate efforts.
            try:
                current_program_output_dir.mkdir()
            except FileExistsError:
                logger.info(f"Skipping: another runner is working on the same seed ({fuzz_d_fuzzer_seed}).")
                continue

            # 10) Load execution trace from disk.
            mutant_execution_traces = [
                (target,
                 MutantTrace.reconstruct_trace_from_disk(trace_path=trace_path,
                                                         source_file_env_var=source_file_env_var))
                for target, trace_path, _ in traced_compilation_results
            ]

            if any(target_trace is None for _, target_trace in mutant_execution_traces):
                logger.error(f"Skipping: execution trace is corrupted. (seed: {fuzz_d_fuzzer_seed}))")
                continue

            # 11) Merge all mutants of consideration traced from different target backends.
            # (Deduplicate mutants with set)
            mutants_covered_by_program = chain.from_iterable(traces for _, traces in mutant_execution_traces)
            mutants_covered_by_program = list(set(mutants_covered_by_program))

            # Sort mutants: since mutants that are sequential in ID are likely to belong in the same mutation group,
            # killing one mutant in the mutation group might lead to kills in the other mutants in the same mutation
            # group.
            mutants_covered_by_program.sort()

            # 12) Discard killed mutants from consideration.
            candidate_mutants_for_program = [(env_var, mutant_id) for (env_var, mutant_id) in mutants_covered_by_program
                                             if (env_var, mutant_id) not in killed_mutants]

            logger.info(
                f"Number of mutants covered by generated program with seed {fuzz_d_fuzzer_seed}: {len(mutants_covered_by_program)}")

            # 13) Perform mutation testing on the generated Dafny program with the mutated Dafny compiler.
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
                    logger.info(
                        f"Skipping: mutant {env_var}:{mutant_id} was killed by another runner or a regression test.")

                logger.info(
                    "[Current session] Surviving mutants: {} | Killed mutants: {}", len(surviving_mutants), len(killed_mutants))
                logger.info(
                    f"Processing mutant {env_var}:{mutant_id} with program generated by seed {fuzz_d_fuzzer_seed}.")

                empty_directory(mutated_compilation_dir)
                shutil.copytree(src=fuzz_d_generation_dir, dst=mutated_compilation_dir)

                # 14) Compile the generated Dafny program with the mutation-instrumented Dafny compiler.
                mutated_compilation_results = {
                    target:
                        target.mutated_compile_to_backend(dafny_binary=mutated_dafny_binary,
                                                          dafny_file_dir=mutated_compilation_dir,
                                                          dafny_file_name=constants.FUZZ_D_GENERATED_FILENAME,
                                                          mutant_env_var=env_var,
                                                          mutant_id=mutant_id,
                                                          timeout_in_seconds=max(float(compilation_timeout_in_seconds),
                                                                                 regular_compile_result.elapsed_time *
                                                                                 COMPILATION_TIMEOUT_SCALE_FACTOR))
                    for target, regular_compile_result in regular_compilation_results.items()
                }

                # 15) Execute the generated Dafny program with the executable artifact produced by
                # mutated Dafny compiler.
                mutated_execution_results = dict()
                if all(result.status == MutantStatus.SURVIVED for _, result in mutated_compilation_results):
                    mutated_execution_results = {
                        target:
                            target.mutant_execution(dafny_file_dir=mutated_compilation_dir,
                                                    dafny_file_name=constants.FUZZ_D_GENERATED_FILENAME,
                                                    default_execution_result=regular_execution_results[
                                                        target].execution_result,
                                                    timeout_in_seconds=max(float(execution_timeout_in_seconds),
                                                                           regular_execution_results[
                                                                               target].elapsed_time *
                                                                           EXECUTION_TIMEOUT_SCALE_FACTOR))
                        for target, result in mutated_compilation_results.items()
                    }

                if len(mutated_execution_results) > 0 and \
                        all(mutant_status == MutantStatus.SURVIVED for mutant_status in
                            mutated_execution_results.values()):
                    mutants_covered_but_not_killed_by_program.append((env_var, mutant_id))
                    logger.info(f"Finished processing mutant {env_var}:{mutant_id}. Kill result: SURVIVED")
                    continue

                # 16) If we reached here, we found a test case to contribute to Dafny! Good work.
                surviving_mutants.remove((env_var, mutant_id))
                killed_mutants.add((env_var, mutant_id))
                mutants_killed_by_program.append((env_var, mutant_id))
                kill_elapsed_time = time.time() - time_of_last_kill
                time_of_last_kill = time.time()
                logger.success(f"Mutant {env_var}:{mutant_id} killed | Killed mutants: {len(killed_mutants)} | "
                               f"Time taken since last kill: {str(kill_elapsed_time)}")

                # Merge the results between compilation and execution of program produced by mutated Dafny compiler.
                mutant_error_statuses = {
                    target: mutated_compilation_results[target].mutant_status
                    if target not in mutated_execution_results else mutated_execution_results[target].mutant_status
                    for target in target_backends
                }

                def persist_kill_info(overall_mutant_status: MutantStatus,
                                      result_dict: Dict[DafnyBackend, MutantStatus], output_dir: Path):
                    # Copy fuzz-d generated program and Dafny compilation artifacts
                    try:
                        output_dir.mkdir()
                        logger.success(
                            f"Kill results for mutant {env_var}:{mutant_id} will be persisted to {str(output_dir / 'kill_info.json')}).")
                        with open(str(output_dir / "kill_info.json"), "w") as killed_file_io:
                            json.dump({"overall_status": overall_mutant_status.name,
                                       "failed_target_backends": [
                                           {"backend": backend.name, "mutant_status": mutant_status.name}
                                           for backend, mutant_status in result_dict.items() if
                                           mutant_status != MutantStatus.SURVIVED
                                       ]},
                                      killed_file_io, indent=4)
                    except FileExistsError:
                        logger.info(
                            f"Skipping: another runner determined this mutant ({env_var}:{mutant_id}) as killed.")

                # 17) Persist kill information to disk
                if any(mutant_status == MutantStatus.KILLED_COMPILER_CRASHED for mutant_status in
                       mutant_error_statuses.values()):
                    persist_kill_info(overall_mutant_status=MutantStatus.KILLED_COMPILER_CRASHED,
                                      result_dict=mutant_error_statuses,
                                      output_dir=mutant_killed_dir)
                elif any(mutant_status == MutantStatus.KILLED_COMPILER_TIMEOUT for mutant_status in
                         mutant_error_statuses.values()):
                    persist_kill_info(overall_mutant_status=MutantStatus.KILLED_COMPILER_TIMEOUT,
                                      result_dict=mutant_error_statuses,
                                      output_dir=mutant_killed_dir)
                elif any(mutant_status == MutantStatus.KILLED_RUNTIME_EXITCODE_DIFFER for mutant_status in
                         mutant_error_statuses.values()):
                    persist_kill_info(overall_mutant_status=MutantStatus.KILLED_RUNTIME_EXITCODE_DIFFER,
                                      result_dict=mutant_error_statuses,
                                      output_dir=mutant_killed_dir)
                elif any(mutant_status == MutantStatus.KILLED_RUNTIME_STDOUT_DIFFER for mutant_status in
                         mutant_error_statuses.values()):
                    persist_kill_info(overall_mutant_status=MutantStatus.KILLED_RUNTIME_STDOUT_DIFFER,
                                      result_dict=mutant_error_statuses,
                                      output_dir=mutant_killed_dir)
                elif any(mutant_status == MutantStatus.KILLED_RUNTIME_STDERR_DIFFER for mutant_status in
                         mutant_error_statuses.values()):
                    persist_kill_info(overall_mutant_status=MutantStatus.KILLED_RUNTIME_STDERR_DIFFER,
                                      result_dict=mutant_error_statuses,
                                      output_dir=mutant_killed_dir)

            # 18) Complete testing current program against all surviving mutants.
            all_mutants_considered_by_program = mutants_killed_by_program + \
                                                mutants_covered_but_not_killed_by_program + \
                                                mutants_skipped_by_program
            all_mutants_considered_by_program.sort()  # there should not be duplicated mutants
            early_termination = mutants_covered_by_program != all_mutants_considered_by_program

            # 19) Persist test campaign summary/metadata.
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
                logger.error(f"Unexpected program internal state. Terminating...")
                exit(1)


def main():
    logger.add("fuzzing_campaign_{time}.log")

    if not validate_volume_directory_exists():
        logger.error('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)

    env = obtain_env_vars()

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action='store_true',
                        help="Perform dry run.")
    parser.add_argument('--seed', type=int,
                        help='Optional. Seed for random number generator. Useful to reproduce results.')
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
                        help='Path to registry generated after instrumenting the Dafny codebase to '
                             'trace mutant executions (.json).')
    parser.add_argument("--passing_tests", type=str,
                        help="Path to file containing lists of passing tests.")
    parser.add_argument("--regression_test_trace_dir", type=str,
                        help="Path to directory containing all mutant execution traces after "
                             "running the Dafny regression test suite.")
    parser.add_argument('--mutation_test_result', type=str,
                        help="Path to mutation testing result of the Dafny regression test suite (.json).")
    parser.add_argument('--source_file_relative_path', type=str,
                        help="Optional. If specified, only consider mutants for the specified file.")
    parser.add_argument('--compilation_timeout', default=30,
                        help='Maximum second(s) allowed to compile generated program with the non-mutated '
                             'Dafny compiler.')
    parser.add_argument('--generation_timeout', default=30,
                        help='Maximum second(s) allowed to generate program with fuzz-d.')
    parser.add_argument('--execution_timeout', default=30,
                        help='Maximum second(s) allowed to execute fuzz-d generated program compiled by the '
                             'non-mutated Dafny compiler.')
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

    source_file_env_var = None
    if args.source_file_relative_path is not None:
        to_find = [registry.env_var for path, registry in
                   mutation_registry.file_relative_path_to_registry.items()
                   if path == args.source_file_relative_path]
        if len(to_find) == 0:
            logger.error("Cannot find the specified file in mutation registry.")
            exit(1)
        elif len(to_find) > 1:
            logger.error(
                "Found more than one match for the specified file in mutation registry. "
                "Mutation registry may be corrupted.")
            exit(1)
        source_file_env_var = to_find[0]

    if args.mutation_test_result is not None:
        mutation_test_results: MutationTestResult | None = \
            MutationTestResult.reconstruct_from_disk(Path(args.mutation_test_result).absolute())
        regression_tests_mutant_traces = None
        if mutation_test_results is None:
            logger.error("Mutation analysis results not found or corrupted.")
            exit(1)

    elif args.passing_tests is not None and args.regression_test_trace_dir is not None:
        # Retrieve execution trace *iff* mutation test results not available.
        # This is an optimisation to fuzz mutants not reachable by the regression test suite.
        mutation_test_results = None
        passing_tests = regression_tests.read_passing_tests(Path(args.passing_tests).absolute())
        regression_tests_mutant_traces = \
            RegressionTestsMutantTraces.reconstruct_trace_from_disk(
                trace_dir=Path(args.regression_test_trace_dir).absolute(),
                test_cases=passing_tests,
                source_file_env_var=source_file_env_var
            )
        if regression_tests_mutant_traces is None:
            logger.error("Mutant trace of regression tests not found or corrupted.")
            exit(1)
    else:
        logger.error("Both regression test execution trace and mutation analysis not made available.")
        exit(1)

    artifact_directory = Path(args.output_directory).absolute()

    if not fuzz_d_binary_path.is_file():
        logger.error("fuzz-d binary not found at {path}.", path=str(fuzz_d_binary_path))
        exit(1)

    if not dafny_binary_path.is_file():
        logger.error("regular dafny binary not found at {path}.", path=str(dafny_binary_path))
        exit(1)

    if not mutated_dafny_binary_path.is_file():
        logger.error("mutated dafny binary not found at {path}.", path=str(mutated_dafny_binary_path))
        exit(1)

    if not traced_dafny_binary_path.is_file():
        logger.error("traced dafny binary not found at {path}.", path=str(traced_dafny_binary_path))
        exit(1)

    # Create output directory if it does not exist
    compilation_artifact_dir = artifact_directory / "compilations"

    tests_artifact_dir = artifact_directory / 'tests'
    regular_compilation_error_dir = artifact_directory / 'regular-compilation-errors'
    regular_wrong_code_dir = artifact_directory / 'regular-wrong-code'
    killed_mutants_artifact_dir = artifact_directory / 'killed_mutants'

    logger.info(f"fuzz-d project root: {fuzz_d_root}")
    logger.info(f"regular dafny project root: {regular_dafny_dir}")
    logger.info(f"mutated dafny project root: {mutated_dafny_dir}")
    logger.info(f"traced dafny project root: {traced_dafny_dir}")
    logger.info(f"compilation artifact output directory: {compilation_artifact_dir}")
    logger.info(f"mutation testing artifact output directory: {tests_artifact_dir}")
    logger.info(f"killed mutants artifact output directory: {killed_mutants_artifact_dir}")
    logger.info(f"regular compilation error output directory: {regular_compilation_error_dir}")
    logger.info(f"regular wrong code bug output directory: {regular_wrong_code_dir}")

    if source_file_env_var is not None:
        logger.info(f"Specified file: {args.source_file_relative_path} | Env var: {source_file_env_var}")

    if args.dry_run:
        logger.info("Dry run complete.")
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
                         DafnyBackend.JAVASCRIPT]
    # DafnyBackend.JAVA]
    # generated programs do not compile with Java backend due to known bugs (fuzz blocker)

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
                                    mutation_registry=mutation_registry,
                                    regression_tests_mutant_traces=regression_tests_mutant_traces,
                                    source_file_env_var=source_file_env_var,
                                    test_campaign_budget_in_hours=args.test_campaign_timeout,
                                    generation_budget_in_seconds=args.generation_timeout,
                                    compilation_timeout_in_seconds=args.compilation_timeout,
                                    execution_timeout_in_seconds=args.execution_timeout)


if __name__ == '__main__':
    main()
