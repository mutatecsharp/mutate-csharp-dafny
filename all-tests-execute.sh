#!/bin/bash

set -uex

TARGET_TRACER=false
MAYBE_NO_BUILD_FLAG=""

usage() {
    echo "Script to execute the Dafny integration test suite."
    echo "Usage: $0 [-e] [-n]"
    echo
    echo "Options:"
    echo "  -e           Target the traced Dafny version."
    echo "  -n           Do not build Dafny."
}

while getopts "enh" opt; do
    case $opt in
        e)
            TARGET_TRACER=true
            ;;
        n)
            MAYBE_NO_BUILD_FLAG="--no-build"
            ;;
        h)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
test -f parallel.runsettings && echo "mutate-csharp-dafny/parallel.runsettings found" || { echo "mutate-csharp-dafny/parallel.runsettings not found"; exit 1; }
source env.sh

# Locate dafny path based on the experiment flag
if $TARGET_TRACER; then
    ARTIFACT_PATH="$TRACED_ARTIFACT_PATH"
    DAFNY_PROJECT_PATH="$TRACED_DAFNY_ROOT"
else
    ARTIFACT_PATH="$MUTATED_ARTIFACT_PATH"
    DAFNY_PROJECT_PATH="$MUTATED_DAFNY_ROOT"
fi

# Set the results directory (todo: categorise based on files)
RESULTS_DIRECTORY="$ARTIFACT_PATH/results/default"
PARALLEL_RUNSETTINGS="$(pwd)/parallel.runsettings"

test -d "$DAFNY_PROJECT_PATH"
test -f "$PARALLEL_RUNSETTINGS"

pushd "$DAFNY_PROJECT_PATH"

# Execute all tests (stop when first test fails)
dotnet test --no-restore "$MAYBE_NO_BUILD_FLAG" --nologo -c Release \
--logger "console;verbosity=normal" \
--results-directory "$RESULTS_DIRECTORY" \
--settings "$PARALLEL_RUNSETTINGS" \
Source/IntegrationTests

popd