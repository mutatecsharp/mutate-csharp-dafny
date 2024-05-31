#!/bin/bash

set -uex

DRY_RUN=""
TRACE=false
MAYBE_NO_BUILD_FLAG=""

usage() {
    echo "Script to execute a specified Dafny integration test case."
    echo "Usage: $0 [-e] [-n] [-d]"
    echo
    echo "Options:"
    echo "  -e           Target the traced Dafny version."
    echo "  -d           Dry run. Test is not executed."
    echo "  -n           Do not build Dafny."
}

while getopts "enhd" opt; do
    case $opt in
        e)
            TRACE=true
            ;;
        n)
            MAYBE_NO_BUILD_FLAG="--no-build"
            ;;
        d)
            DRY_RUN="--list-tests" # dry run: true
            ;;
        h)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

TESTCASE=$1

test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
source env.sh

# Locate dafny path based on the experiment flag
if $TRACE; then
    ARTIFACT_PATH="$TRACED_ARTIFACT_PATH"
    DAFNY_PROJECT_PATH="$TRACED_DAFNY_ROOT"
else
    ARTIFACT_PATH="$MUTATED_ARTIFACT_PATH"
    DAFNY_PROJECT_PATH="$MUTATED_DAFNY_ROOT"
fi

# Set the results directory (todo: categorise based on files)
RESULTS_DIRECTORY="$ARTIFACT_PATH/single-run-results/"
SEQUENTIAL_RUNSETTINGS="$(pwd)/sequential.runsettings"

test -d "$DAFNY_PROJECT_PATH"
test -f "$SEQUENTIAL_RUNSETTINGS"

pushd "$DAFNY_PROJECT_PATH"

# Execute specified test
dotnet test --no-restore "$MAYBE_NO_BUILD_FLAG" --nologo -c Release \
--logger "console;verbosity=normal" \
--results-directory "$RESULTS_DIRECTORY" \
--settings "$SEQUENTIAL_RUNSETTINGS" \
--filter "DisplayName=$TESTCASE" \
$DRY_RUN \
Source/IntegrationTests

popd