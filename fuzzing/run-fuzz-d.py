#! /usr/bin/env python3.11

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

from fuzzing.util.mutation_registry import MutationRegistry
from fuzzing.util.instrument_type import InstrumentType
from fuzzing.util.run_subprocess import run_subprocess


LONG_UPPER_BOUND = (1 << 64) - 1
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
                  timeout_in_seconds: int,
                  env_dict=None) -> (bool, float):
    # Compiles the program with the Dafny compiler and produces an executable artifact.
    compile_command = [str(dafny_binary), "build", "--no-verify", "--output", str(executable_output_path), str(dafny_file_path)]

    start_time = time.time()
    (exit_code, stdout, stderr, timeout) = run_subprocess(compile_command, timeout_in_seconds, env=env_dict)
    elapsed_time = time.time() - start_time

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


def execute_compiled_program(compiled_program_binary: Path,
                             dafny_type: InstrumentType,
                             timeout_in_seconds: int) -> (bool, float):
    # Executes the binary resulting from Dafny compilation.
    execute_binary_command = [str(compiled_program_binary)]

    start_time = time.time()
    (exit_code, stdout, stderr, timeout) = run_subprocess(execute_binary_command, timeout_in_seconds)
    elapsed_time = time.time() - start_time

    if timeout:
        print(f"Skipping: timeout while running executable of generated program. ({dafny_type.name})")
        return False, None

    if exit_code != 0:
        print(f"Skipping: error while running executable of generated program. ({dafny_type.name})")

    return True, elapsed_time


def mutation_guided_test_generation(fuzz_d_binary: Path,
                                    default_dafny_binary: Path,
                                    mutated_dafny_binary: Path,
                                    traced_dafny_binary: Path,
                                    artifact_path: Path,
                                    mutation_registry: MutationRegistry,
                                    test_campaign_budget_in_hours: int,
                                    generation_budget_in_seconds: int,
                                    default_compilation_timeout_in_seconds: int):
    # Mutation testing
    killed_mutants: set = set()
    surviving_mutants: set = set()  # todo: update with candidates

    test_campaign_start_time = time.time()  # in seconds

    with tempfile.TemporaryDirectory(dir=str(artifact_path)) as temp_dir:
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
                test_campaign_budget_in_hours=test_campaign_budget_in_hours):
            fuzz_d_fuzzer_seed = random.randint(0, LONG_UPPER_BOUND)

            # todo: delete compilations
            # 1) Generate a valid Dafny program
            if not execute_fuzz_d(fuzz_d_binary,
                                  fuzz_d_generation_dir,
                                  fuzz_d_fuzzer_seed,
                                  generation_budget_in_seconds):
                continue

            if not fuzz_d_output_path.is_file():
                print("Skipping: fuzz-d generated output not found. Check if setup is correct.")
                continue

            # 2) Compile the generated Dafny program with the default Dafny compiler
            default_compile_success, compile_elapsed_time = \
                execute_dafny(dafny_binary=default_dafny_binary,
                              dafny_file_path=fuzz_d_output_path,
                              executable_output_path=default_compiled_executable_path,
                              dafny_type=InstrumentType.DEFAULT,
                              timeout_in_seconds=default_compilation_timeout_in_seconds)
            if not default_compile_success:
                continue

            # 4) Execute the generated Dafny program with the executable artifact produced.


            # 4) Compile the generated Dafny program with the trace-instrumented Dafny compiler.
            env_dict = os.environ.copy()
            env_dict[EXECUTION_TRACE_OUTPUT_ENV_VAR] = str(mutant_trace_file_path)
            traced_compile_success, _ = \
                execute_dafny(dafny_binary=traced_dafny_binary,
                              dafny_file_path=fuzz_d_output_path,
                              executable_output_path=traced_compiled_executable_path,
                              dafny_type=InstrumentType.TRACED,
                              timeout_in_seconds=default_compilation_timeout_in_seconds,
                              env_dict=env_dict)
            if not traced_compile_success:
                continue
            if not mutant_trace_file_path.exists():
                print("Skipping: either the generated program execution trace does not cover any mutants, or injection of trace output path environment variable failed. If this persists, check if the injection performs as expected.")
                continue

            # 5) Create directory to perform mutation testing, using seed number to deduplicate efforts.


            # 5) Perform mutation testing on the generated Dafny program with the mutated Dafny compiler.



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
    artifact_directory.mkdir(parents=True, exist_ok=True)

    mutation_guided_test_generation(fuzz_d_binary=fuzz_d_binary_path,
                                    default_dafny_binary=dafny_binary_path,
                                    mutated_dafny_binary=mutated_dafny_binary_path,
                                    traced_dafny_binary=traced_dafny_binary_path,
                                    artifact_path=args.output_directory,
                                    mutation_registry=mutation_registry,
                                    test_campaign_budget_in_hours=args.test_campaign_timeout,
                                    generation_budget_in_seconds=args.generation_timeout,
                                    default_compilation_timeout_in_seconds=args.compilation_timeout)


if __name__ == '__main__':
    main()
