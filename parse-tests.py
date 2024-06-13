#!/usr/bin/env python3.11

import argparse

from pathlib import Path
from loguru import logger

SUPPORTED_FRAMEWORK={"nunit", "mstest"}

escape_dict = {
    '\\': r'\\',
    '(': r'\(',
    ')': r'\)',
    '&': r'\&',
    '|': r'\|',
    '=': r'\=',
    '!': r'\!',
    '~': r'\~'
}

# decided to not break it down more granularly because of the test framework overhead
# fully qualified name for nunit
# https://github.com/Microsoft/vstest-docs/blob/main/docs/filter.md
#https://stackoverflow.com/questions/69688927/filter-dotnet-test-when-the-f-test-name-contains-a-space-character/74790349#74790349
def parse_tests_to_fqn_nunit(test_name: str) -> str:
    name_components = test_name.strip().split('(')[0].split()  # split by whitespace
    return '&'.join(name_components)

# regular name
def parse_tests_to_name_mstest(test_name: str) -> str:
    name_components = test_name.strip()
    insert_escape_char = []
    for component in name_components:
        if component in escape_dict:
            insert_escape_char.append(escape_dict[component])
        else:
            insert_escape_char.append(component)
    return ''.join(insert_escape_char)

def refactor_testname(framework: str, input_file: Path, output_file: Path):
    with input_file.open('r') as file:
        lines = file.readlines()

    # Make test cases FQN ready
    if framework == "nunit":
        parsed_testcases = list(set([parse_tests_to_fqn_nunit(line) for line in lines]))
    # Make test cases name ready
    elif framework == "mstest":
        parsed_testcases = list(set([parse_tests_to_name_mstest(line) for line in lines]))

    with output_file.open('w') as file:
        for testcase in parsed_testcases:
            file.write(testcase + '\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", type=str, required=True,
                        help="Test target framework. Supports: nunit, mstest.")
    parser.add_argument("--passing-tests", type=Path, required=True,
                        help="Path to list of names of passing tests.")

    args = parser.parse_args()

    if not args.framework in SUPPORTED_FRAMEWORK:
        logger.error(f"Framework {args.framework} is not supported.")
        raise argparse.ArgumentTypeError(f"Unsupported framework: {args.framework}")

    input_path: Path = args.passing_tests.resolve()

    if not input_path.exists():
        logger.error("File does not exist at {}.", str(input_path))

    output_path = input_path.parent / f"{input_path.name}-parsed"
    refactor_testname(args.framework, input_path, output_path)
