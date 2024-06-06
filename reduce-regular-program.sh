#!/bin/bash

set -uex

usage() {
    echo "Script to reduce Dafny programs containing wrong code bugs."
    echo ""
    echo "Options:"
    echo "$0 [-d]"
    echo ""
    echo "-d        Dry run."
}

DRY_RUN=""

while getopts "hdu" opt; do
    case $opt in
        d)
            DRY_RUN="--dry-run"
            ;;
        h)
            usage
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
source env.sh

# Sanity check: perses submodule is cloned
test -f third_party/perses/.bazelrc && echo "perses cloned" || { echo "perses not found"; exit 1; }

# Sanity check: latest commit Dafny repository is present
LATEST_COMMIT_DAFNY_ROOT="$VOLUME_ROOT/latest-commit/dafny"
test -d "$LATEST_COMMIT_DAFNY_ROOT"
test -d "$MUTATE_DAFNY_RECORDS_ROOT/fuzzer_output/regular-wrong-code"

REDUCER_SCRIPT="$(pwd)/reducer/reduce-program.py"
test -f "$REDUCER_SCRIPT"

# Obtain records.
FUZZER_OUTPUT_RECORDS="$MUTATE_DAFNY_RECORDS_ROOT/fuzzer_output"
test -d "$FUZZER_OUTPUT_RECORDS"

PERSES_PATH="$(pwd)/third_party/perses"
test -d "$PERSES_PATH"

WORKER_COUNT=4

echo "reduce wrong code bugged programs with the regular Dafny compiler."
PYTHONPATH=$(pwd) \
$REDUCER_SCRIPT $DRY_RUN \
--perses "$PERSES_PATH" \
--latest_dafny "$LATEST_COMMIT_DAFNY_ROOT" \
--fuzzer_output "$MUTATE_DAFNY_RECORDS_ROOT/fuzzer_output"

echo "complete."