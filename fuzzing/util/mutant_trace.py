from util.regression_tests import get_valid_test_file_name

from pathlib import Path
from typing import List, Dict, Set, Tuple

class MutantTrace:
    @staticmethod
    def reconstruct_trace_from_disk(trace_path: Path, source_file_env_var: str | None) -> List[Tuple[str, str]] | None:
        with open(trace_path, 'r') as mutant_trace_io:
            mutants_covered_by_program = mutant_trace_io.readlines()

        mutants_covered_by_program = [MutantTrace.parse_recorded_trace(trace.strip()) for trace
                                      in mutants_covered_by_program]
        # remove duplicates
        mutants_covered_by_program = list(set(mutants_covered_by_program))

        if any(env_var_to_mutant_id is not None for env_var_to_mutant_id in mutants_covered_by_program):
            return None

        # Filter for particular source file under test if specified and discard killed mutants from consideration.
        if source_file_env_var is not None:
            mutants_covered_by_program = [(env_var, mutant_id) for (env_var, mutant_id) in
                                          mutants_covered_by_program if env_var == source_file_env_var]
        return mutants_covered_by_program

    @staticmethod
    def parse_recorded_trace(trace: str) -> Tuple[str, str] | None:
        individual_trace: List[str] = trace.split(':')
        if len(individual_trace) != 2:
            return None
        env_var, mutant_id = individual_trace
        if not env_var.startswith("MUTATE_CSHARP_ACTIVATED_MUTANT"):
            return None
        return env_var, mutant_id


class RegressionTestsMutantTraces:
    @staticmethod
    def reconstruct_trace_from_disk(trace_dir: Path, test_cases: List[str], source_file_env_var: str | None) \
            -> Dict[str, Set[Tuple[str, str]]] | None:
        execution_traces_of_tests: Dict[str, Set[Tuple[str, str]]] = dict()

        for test_name in test_cases:
            test_trace_path = trace_dir / get_valid_test_file_name(test_name)

            if not test_trace_path.exists():
                continue

            with test_trace_path.open('r') as mutant_trace_io:
                all_traces = mutant_trace_io.readlines()

            all_traces = [MutantTrace.parse_recorded_trace(trace.strip()) for trace in all_traces]

            if any(test_trace is None for test_trace in all_traces):
                return None

            if source_file_env_var is not None:
                all_traces = [(env_var, mutant_id) for env_var, mutant_id in all_traces
                              if env_var == source_file_env_var]

            execution_traces_of_tests[test_name] = set(all_traces)

        return execution_traces_of_tests
