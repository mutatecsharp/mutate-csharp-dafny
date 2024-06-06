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
ONLY_TEST_UNCOVERED=""

while getopts "hdu" opt; do
    case $opt in
        d)
            DRY_RUN="--dry-run"
            ;;
        u)
            ONLY_TEST_UNCOVERED="true"
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
test -f basic.runsettings && echo "mutate-csharp-dafny/basic.runsettings found" || { echo "mutate-csharp-dafny/basic.runsettings not found"; exit 1; }
source env.sh

# Sanity check: fuzz-d submodule is cloned recursively
test -f third_party/fuzz-d/run.py && echo "fuzz-d cloned" || { echo "fuzz-d not found"; exit 1; }
test -f third_party/fuzz-d/app/src/main/antlr/dafny.g4 && echo "fuzz-d submodules cloned" || { echo "fuzz-d submodules not found"; exit 1; }

MUTATE_CSHARP_PATH="$WORKSPACE_MUTATE_CSHARP_ROOT"

test -d "$MUTATE_CSHARP_PATH"

# Sanity check: repository mutated / traced
test -f "$MUTATED_DAFNY_ROOT/Source/DafnyCore/registry.mucs.json"
test -f "$TRACED_DAFNY_ROOT/Source/DafnyCore/tracer-registry.mucs.json"
test -f "$MUTATE_DAFNY_RECORDS_ROOT/passing-tests.txt"

FUZZER_SCRIPT="$(pwd)/fuzzing/run-fuzzer-campaign.py"
test -f "$FUZZER_SCRIPT"

FUZZER_OUTPUT_DIR="$VOLUME_ROOT/fuzzer_output"
mkdir -p "$FUZZER_OUTPUT_DIR"

# Copy the killed mutants information from regression testing.
if [ -n "$DRY_RUN" ]; then
  rsync -a "$VOLUME_ROOT/output/killed_mutants/" "$FUZZER_OUTPUT_DIR/killed_mutants"
  pushd third_party/fuzz-d
  ./gradlew build
  popd
fi

# Run fuzzing campaign to catch bugs and generate tests that kill mutants.
# Focus on SinglePassCodeGenerator.cs.
SOURCE_FILE_UNDER_TEST="Backends/SinglePassCodeGenerator.cs"
WORKER_COUNT=32

if [ $ONLY_TEST_UNCOVERED ]; then
  echo "only fuzz mutants unreachable by regression test suite."
  $FUZZER_SCRIPT $DRY_RUN \
  --source_file_relative_path \
  "Backends/SinglePassCodeGenerator.cs" \
  "Backends/CSharp/CsharpCodeGenerator.cs" \
  "Backends/JavaScript/JavaScriptCodeGenerator.cs" \
  --passing_tests "$MUTATE_DAFNY_RECORDS_ROOT/passing-tests.txt" \
  --regression_test_trace_dir "$TRACED_ARTIFACT_PATH/execution-trace" \
  --output_directory "$FUZZER_OUTPUT_DIR"
else
  echo "fuzz all survived mutants."
  for _ in $(seq 1 $WORKER_COUNT); do
    $FUZZER_SCRIPT $DRY_RUN \
    --source_file_relative_path \
    "Backends/SinglePassCodeGenerator.cs" \
    "Backends/CSharp/CsharpCodeGenerator.cs" \
    "Backends/JavaScript/JavaScriptCodeGenerator.cs" \
    --output_directory "$FUZZER_OUTPUT_DIR" \
    --mutation_test_result \
    "$MUTATE_DAFNY_RECORDS_ROOT/mutation-test/CsharpCodeGenerator/mutation-testing.mucs.json" \
    "$MUTATE_DAFNY_RECORDS_ROOT/mutation-test/JavaScriptCodeGenerator/mutation-testing.mucs.json" \
    "$MUTATE_DAFNY_RECORDS_ROOT/mutation-test/SinglePassCodeGenerator/mutation-testing.mucs.json" \
  & done
fi
