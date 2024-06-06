#! /usr/bin/env python3.11
# To execute this script, run python -m fuzzing.util.constants $0

import sys
import stat
import os
import shlex
import shutil
import subprocess
import argparse
import jinja2
import threading

from collections import deque
from loguru import logger
from pathlib import Path
from typing import Dict
from util.candidate_test import FuzzdCandidateTest
from util.regular_error_result import RegularErrorResult
from fuzzing.util.run_subprocess import run_subprocess
from fuzzing.util.program_status import RegularProgramStatus


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


def read_output(stream, output_type):
    while True:
        output = stream.readline()
        if output:
            if output_type == "STDOUT":
                logger.info(output)
            elif output_type == "STDERR":
                logger.error(output)
        else:
            break


# Only focus on reducing programs that are executable and does not time out.
def retrieve_regular_failed_programs(regular_wrong_code_dir: Path) -> Dict[FuzzdCandidateTest, RegularErrorResult]:
    failed_programs: Dict[FuzzdCandidateTest, RegularErrorResult] = dict()

    for program_dir in regular_wrong_code_dir.iterdir():
        error_info = program_dir / "regular_error.json"
        # Verify program directory results from fuzzer-generated tests.
        # logger.debug(program_dir.name)
        if not program_dir.name.startswith("fuzzd") or not error_info.exists():
            # logger.debug("cannot find error summary for {}.", program_dir.name)
            continue
        # Verify Dafny program exists in directory.
        if not (program_dir / "fuzz_d_generation" / "main.dfy").exists():
            # logger.debug("cannot find dafny program for {}.", program_dir.name)
            continue
        error_result = RegularErrorResult.reconstruct_error_from_disk(program_dir / "regular_error.json")
        if error_result is None:
            # logger.debug("cannot reconstruct error summary for {}.", program_dir.name)
            continue
        if error_result.overall_status == RegularProgramStatus.RUNTIME_TIMEOUT:
            continue
        failed_programs[FuzzdCandidateTest(program_dir)] = error_result

    return failed_programs


def validate_initial_results(candidate_program: FuzzdCandidateTest,
                             regular_dafny_dir: Path,
                             result: RegularErrorResult) -> bool:
    # We focus on wrong code bugs so this is not interesting.
    if result.overall_status == RegularProgramStatus.RUNTIME_TIMEOUT or \
        result.overall_status == RegularProgramStatus.COMPILER_TIMEOUT or \
            result.overall_status == RegularProgramStatus.COMPILER_EXITCODE_NON_ZERO:
                return False
    
    # Execute to get results.
    with tempfile
    
    results = {
        backend: backend.regular_execution(backend_artifact_dir=candidate_program.)
    }
    
    
    
    
    if result.overall_status == RegularProgramStatus.RUNTIME_EXITCODE_NON_ZERO:
        result = {
            backend: backend.regular_execution
        }

def reduce_wrong_code_program(perses_dir: Path,
                              latest_dafny_dir: Path,
                              candidate_program: FuzzdCandidateTest,
                              result: RegularErrorResult,
                              reduced_output_dir: Path,
                              timeout_in_seconds: int):
    interesting_script_path = reduced_output_dir / "interesting.py"
    reduce_candidate_program_path = reduced_output_dir / f"{candidate_program.program_name}.dfy"

    # Check if reduction has been performed.
    try:
        reduced_output_dir.mkdir()
        shutil.copy(src=candidate_program.program_path, dst=reduce_candidate_program_path)
    except FileExistsError:
        logger.info("Skipping reduction for program {} as reduction for the program has been performed.",
                   candidate_program.program_dir.name)
        return

    logger.info("Reducing candidate program {} with the expected erratic behaviour: {}.",
               candidate_program.program_dir.name,
               result.overall_status.name)

    # Generate template.
    perses_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            searchpath=os.path.dirname(os.path.realpath(__file__)))).get_template(
        "util/regular_wrong_code_template.py.jinja2")

    # Render the interesting script with values.
    with interesting_script_path.open("w", encoding='utf-8') as template_io:
        rendered_template = perses_template.render(
            latest_dafny=latest_dafny_dir,
            dafny_file_name=candidate_program.program_name,
            regular_compilation_timeout=30,
            regular_execution_timeout=30,
            overall_error_status=result.overall_status.name
        )
        template_io.write(rendered_template)

    # Make the interestingness test executable.
    st = os.stat(interesting_script_path)
    os.chmod(interesting_script_path, st.st_mode | stat.S_IEXEC)

    # Commence reduction.
    reduction_command = ["java", "-jar", str(perses_dir / "bazel-bin/src/org/perses/perses_deploy.jar"),
                            "--test-script", str(interesting_script_path),
                            "--input-file", str(reduce_candidate_program_path)]
    reduction_process = subprocess.Popen(reduction_command, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True)
    
    # Reduction may take a while - we track real-time progress by printing stdout / stderr.
    stdout_thread = threading.Thread(target=read_output, args=(reduction_process.stdout, "STDOUT"))
    stderr_thread = threading.Thread(target=read_output, args=(reduction_process.stderr, "STDERR"))
    stdout_thread.start()
    stderr_thread.start()
    
    # Wait for the process to complete or timeout.
    try:
        reduction_process.wait(timeout=timeout_in_seconds)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(reduction_process.pid), signal.SIGTERM)
        logger.error("Perses timed out for program {}.", candidate_program.program_name)
    finally:
        stdout_thread.join()
        stderr_thread.join()
        
    if reduction_process.returncode != 0:
        logger.error("Perses failed to reduce program {}.", candidate_program.program_name)
    else:
        logger.success("Successfully reduced program {}!", candidate_program.program_name)


def main():
    logger.add("program_reducer_queue.log")

    if not validate_volume_directory_exists():
        logger.error('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)

    env = obtain_env_vars()

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Perform dry run.")
    parser.add_argument("--reduce_mutant", action="store_true",
                        help="Optional. Reduce mutants if specified.")
    parser.add_argument("--fuzzer_output", type=Path,
                        help="Path to the fuzzer output directory containing Dafny programs that uncover bugs in the compiler.")
    parser.add_argument("--latest_dafny", type=Path,
                        help='Path to the Dafny project with the latest commit.')
    # parser.add_argument("regular_dafny", type=Path,
    #                     help="Path to the non-mutated Dafny.")
    # parser.add_argument("mutated_dafny", type=Path,
    #                     help="Path to the mutated Dafny.")
    parser.add_argument("--perses", type=Path,
                        help="Path to the root directory of the program reducer, Perses.")
    parser.add_argument("--individual_reduction_timeout", type=int, default=43200,
                        help="Time in seconds for individual program reduction timeout.")

    args = parser.parse_args()

    if args.fuzzer_output is not None:
        fuzzer_output_dir = args.fuzzer_output
    else:
        fuzzer_output_dir = Path(f"{env['VOLUME_ROOT']}/fuzzer_output").resolve()

    regular_wrong_code_dir = fuzzer_output_dir / 'regular-wrong-code'
    killing_tests_dir = fuzzer_output_dir / "killing_tests"

    # Directory to persist program reduction results.
    if not args.reduce_mutant:
        reduction_artifact_dir = Path(f"{env['VOLUME_ROOT']}/wrong-code-reduction-output").resolve()
    else:
        reduction_artifact_dir = Path(f"{env['VOLUME_ROOT']}/mutant-reduction-output").resolve()

    # Validation checks
    if not fuzzer_output_dir.is_dir():
        logger.error("Fuzzer output directory not found at {}.", str(fuzzer_output_dir))
        exit(1)

    if args.latest_dafny:
        latest_dafny_dir = args.latest_dafny.resolve()
    else:
        latest_dafny_dir = Path(f"{env['VOLUME_ROOT']}/latest-commit/dafny").resolve()
    if not latest_dafny_dir.is_dir():
        logger.error("Cannot find dafny directory at {}.", str(latest_dafny_dir))
        exit(1)
    logger.info("latest dafny dir: {}", latest_dafny_dir)

    perses_dir = Path(args.perses).resolve()
    logger.info("perses dir: {}", perses_dir)

    regular_dafny = None #todo
    mutated_dafny = None #todo

    if args.reduce_mutant:
        pass  # TODO
        # if not args.regular_dafny.is_dir() or not args.mutated_dafny.is_dir():
        #     logger.error("To reduce mutants, regular and mutated Dafny compiler path should be supplied.")
        #     exit(1)
        # if not killing_tests_dir.is_dir():
        #     logger.error("Killing tests directory not found.")
        #     exit(1)
        # regular_dafny = args.regular_dafny.resolve()
        # mutated_dafny = args.mutated_dafny.resolve()
        # logger.info("regular dafny path: {}", str(regular_dafny))
        # logger.info("mutated dafny path: {}", str(mutated_dafny))
        # failed_programs = retrieve_mutated_failed_programs(killing_tests_dir)
    else:
        logger.info("wrong code dir: {}", regular_wrong_code_dir)
        if not regular_wrong_code_dir.is_dir():
            logger.error("Fuzzer output directory is empty. Run the fuzzer to populate programs.",
                         str(fuzzer_output_dir))
            exit(1)
        failed_programs = retrieve_regular_failed_programs(regular_wrong_code_dir)

    logger.info("The following tests are found to uncover bugs in the Dafny compiler:")
    for program in failed_programs.keys():
        logger.info(program.program_dir.name)

    if args.dry_run:
        logger.info("Dry run complete.")
        return

    reduction_artifact_dir.mkdir(parents=True, exist_ok=True)
    reduction_queue = deque()
    for candidate_program, result in failed_programs.items():
        reduction_queue.append((candidate_program, result))

    logger.info("Found {} programs with execution time erratic behaviours to reduce.", len(reduction_queue))
    programs_reduced = 0
    total_programs_to_reduce = len(reduction_queue)

    if not args.reduce_mutant:
        while len(reduction_queue) > 0:
            candidate_program, result = reduction_queue.popleft()
            logger.info("Attempting to reduce regular wrong code bug program {} ({}/{} candidates)",
                        candidate_program.program_dir.name,
                        programs_reduced,
                        total_programs_to_reduce)
            reduced_output_dir = reduction_artifact_dir / candidate_program.program_dir.name
            reduce_wrong_code_program(perses_dir=perses_dir,
                                      latest_dafny_dir=latest_dafny_dir,
                                      candidate_program=candidate_program,
                                      result=result,
                                      reduced_output_dir=reduced_output_dir,
                                      timeout_in_seconds=args.individual_reduction_timeout)
            programs_reduced += 1


if __name__ == "__main__":
    main()
