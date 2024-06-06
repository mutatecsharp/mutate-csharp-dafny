import json

from enum import Enum
from pathlib import Path
from loguru import logger
from itertools import chain

class MutationTestStatus(Enum):
    Nothing = 1
    Killed = 2
    Survived = 3
    Skipped = 4
    Timeout = 5
    Uncovered = 6


class MutationTestResult:
    def __init__(self, raw_json):
        if 'MutantStatus' in raw_json:
            self.mutant_status = {mutant: MutationTestStatus[status] for mutant, status
                                in raw_json['MutantStatus'].items() if status != "None"}
        else:
            self.mutant_status = dict()

    @staticmethod
    def reconstruct_from_disk(path: Path):
        if not path.exists() or not path.name.endswith('mutation-testing.mucs.json'):
            logger.error("Mutation test result does not exist.")
            exit(1)

        with path.open(mode='r') as f:
            result_json = json.load(f)

        return MutationTestResult(result_json)

    @staticmethod
    def merge_results(results: list):  # list of mutation test results
        # Sanity check: all mutants from the list should be unique
        all_mutants = []
        for mutation_analysis in results:
            all_mutants.extend(list(mutation_analysis.mutant_status.keys()))

        if len(set(all_mutants)) != len(all_mutants):
            logger.error("Mutation test result contains duplicate mutants.")
            exit(1)

        mutation_result = MutationTestResult(dict())

        all_results = dict()
        for result in results:
            all_results.update(result.mutant_status)
        mutation_result.mutant_status = all_results

        return mutation_result


    # Mutant of format "ENV_VAR:ID"
    def get_mutant_status(self, mutant: str) -> MutationTestStatus:
        return self.mutant_status[mutant]

    def get_mutants_of_status(self, query_status: MutationTestStatus) -> list:
        return [mutant for mutant, status in self.mutant_status.items() if status == query_status]
