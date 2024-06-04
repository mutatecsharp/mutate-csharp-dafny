#!/bin/bash

set -uex

usage() {
    echo "Script to run mutation testing for the Dafny compiler."
    echo ""
    echo "Options:"
    echo "$0 [-d]"
    echo ""
    echo "-d        Dry run."
}

DRY_RUN=""

while getopts "hd" opt; do
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
test -f parallel.runsettings && echo "mutate-csharp-dafny/parallel.runsettings found" || { echo "mutate-csharp-dafny/parallel.runsettings not found"; exit 1; }
source env.sh

# Sanity check: fuzz-d submodule is cloned recursively
test -f third_party/fuzz_d/run.py && echo "fuzz-d cloned" || { echo "fuzz-d not found"; exit 1; }
test -f third_party/fuzz_d/app/src/main/antlr/dafny.g4 && echo "fuzz-d submodules cloned" || { echo "fuzz-d submodules not found"; exit 1; }

MUTATE_CSHARP_PATH="$WORKSPACE_MUTATE_CSHARP_ROOT"

test -d "$MUTATE_CSHARP_PATH"

# Sanity check: repository mutated / traced
test -f "$MUTATED_DAFNY_ROOT/Source/DafnyCore/registry.mucs.json"
test -f "$TRACED_DAFNY_ROOT/Source/DafnyCore/tracer-registry.mucs.json"

FUZZER_SCRIPT="$(pwd)/fuzzing/run-fuzzer-campaign.py"
test -f "$FUZZER_SCRIPT"

FUZZER_OUTPUT_DIR="$VOLUME_ROOT/fuzzer_output"
mkdir -p "$FUZZER_OUTPUT_DIR"

# Copy the killed mutants information from regression testing.
if [ -n "$DRY_RUN" ]; then
  rsync -a "$VOLUME_ROOT/output/killed_mutants/" "$FUZZER_OUTPUT_DIR/killed_mutants"
fi

# Run fuzzing campaign to catch bugs and generate tests that kill mutants.
$FUZZER_SCRIPT "$DRY_RUN" \
--output_directory "$FUZZER_OUTPUT_DIR" \
--mutation_test_result "$INTEGRATION_TEST_PATH/mutation-testing.mucs.json"
