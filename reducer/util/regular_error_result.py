import json

from typing import Dict
from pathlib import Path
from loguru import logger

from fuzzing.util.program_status import RegularProgramStatus
from fuzzing.dafny import DafnyBackend


class RegularErrorResult:
    def __init__(self, raw_json):
        self.overall_status: RegularProgramStatus = RegularProgramStatus[raw_json['overall_status']]
        self.failed_target_backends: Dict[DafnyBackend, RegularProgramStatus] = {
            DafnyBackend[entry['backend']]:
                RegularProgramStatus[entry['program_status']]
            for entry in raw_json['failed_target_backends']
        }
        if "exit_codes" in raw_json:
            self.exit_codes: Dict[DafnyBackend, int] | None = {
                DafnyBackend[entry['backend']]: entry['exit_code']
                for entry in raw_json['exit_codes']
            }
        else:
            self.exit_codes = None

        # don't keep a reference of the stdout and stderr in memory

    @staticmethod
    def reconstruct_error_from_disk(error_file: Path):
        if not error_file.is_file() or not error_file.name.startswith("regular_error.json"):
            return None

        with error_file.open('r') as error_io:
            error_json = json.load(error_io)

        return RegularErrorResult(error_json)
