from pathlib import Path


class MutantTrace:
    @staticmethod
    def reconstruct_trace_from_disk(trace_path: Path, source_file_env_var: str | None) -> list | None:
        with open(trace_path, 'r') as mutant_trace_io:
            # remove duplicates
            mutants_covered_by_program = list(set([tuple(line.strip().split(':'))
                                                   for line in mutant_trace_io.readlines()]))

        if not all(len(env_var_to_mutant_id) == 2 for env_var_to_mutant_id in mutants_covered_by_program):
            return None

        # Filter for particular source file under test if specified and discard killed mutants from consideration.
        if source_file_env_var is not None:
            mutants_covered_by_program = [(env_var, mutant_id) for (env_var, mutant_id) in
                                          mutants_covered_by_program if env_var == source_file_env_var]
        return mutants_covered_by_program
