from pathlib import Path
from fuzzing.util.constants import INVALID_FILE_NAME_CHARACTERS


def read_passing_tests(tests_list: Path):
    with tests_list.open('r') as f:
        passing_tests = f.read().splitlines()
    passing_tests = [test.strip() for test in passing_tests]

    return passing_tests


def get_valid_test_file_name(test_name: str) -> str:
    return ''.join(ch for ch in test_name if ch not in INVALID_FILE_NAME_CHARACTERS)
