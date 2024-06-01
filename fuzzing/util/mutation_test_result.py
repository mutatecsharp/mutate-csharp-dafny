import json

from enum import Enum
from pathlib import Path


class MutationTestStatus(Enum):
    Nothing = 1
    Killed = 2
    Survived = 3
    Skipped = 4
    Timeout = 5
    Uncovered = 6


class MutationTestResult:
    def __init__(self, raw_json):
        self.test_results_of_mutants = raw_json['MutantTestResultsOfTestCases']
        self.mutant_status = {mutant: MutationTestStatus[status] for mutant, status
                              in raw_json['MutantStatus'].items() if status != "None"}

    @staticmethod
    def reconstruct_from_disk(path: Path):
        if not path.exists() or not path.name.endswith('.json'):
            print("Mutation test result does not exist.")
            exit(1)

        with path.open(mode='r') as f:
            result_json = json.load(f)

        return MutationTestResult(result_json)

    # Mutant of format "ENV_VAR:ID"
    def get_mutant_status(self, mutant: str) -> MutationTestStatus:
        return self.mutant_status[mutant]

    def get_mutants_of_status(self, query_status: MutationTestStatus) -> list:
        return [mutant for mutant, status in self.mutant_status.items() if status == query_status]
