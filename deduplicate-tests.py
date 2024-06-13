#!/usr/bin/env python3.11

import argparse

from pathlib import Path
from loguru import logger

def extract_substrings(input_file: Path, output_file: Path):
    with input_file.open('r') as file:
        lines = file.readlines()

    # Perform deduplication after stripping parameters from tests
    substrings = list(set([line.split('(')[0].strip() for line in lines]))

    with output_file.open('w') as file:
        for substring in substrings:
            file.write(substring + '\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--passing-tests", type=Path, required=True,
                        help="Path to list of names of passing tests.")

    args = parser.parse_args()
    input_path: Path = args.passing_tests.resolve()

    if not input_path.exists():
        logger.error("File does not exist at {}.", str(input_path))

    output_path = input_path.parent / f"{input_path.name}-parsed"
    extract_substrings(input_path, output_path)
