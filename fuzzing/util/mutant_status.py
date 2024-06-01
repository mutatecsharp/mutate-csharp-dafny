from enum import Enum


class MutantStatus(Enum):
    KILLED_COMPILER_CRASHED = 1
    KILLED_COMPILER_TIMEOUT = 2
    KILLED_COMPILER_MISSING_EXECUTABLE_OUTPUT = 3
    KILLED_RUNTIME_TIMEOUT = 4
    KILLED_RUNTIME_EXITCODE_DIFFER = 5
    KILLED_RUNTIME_STDOUT_DIFFER = 6
    KILLED_RUNTIME_STDERR_DIFFER = 7
    SURVIVED_HASH_EQUIVALENT = 8
    SURVIVED_HASH_DIFFER = 9
