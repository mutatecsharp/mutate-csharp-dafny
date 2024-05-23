#!/bin/bash

set -uex

EXPERIMENT=false
MAYBE_NO_BUILD_FLAG=""

usage() {
    echo "Script to execute a specified Dafny integration test case."
    echo "Usage: $0 [-e] [-n]"
    echo
    echo "Options:"
    echo "  -e           Target the clean Dafny version."
    echo "  -n           Do not build Dafny."
}

while getopts "enh" opt; do
    case $opt in
        e)
            EXPERIMENT=true
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

TESTCASE=$1

test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
source env.sh

# Locate dafny path based on the experiment flag
if $EXPERIMENT; then
    ARTIFACT_PATH="$EXPERIMENT_ARTIFACT_PATH"
    DAFNY_PROJECT_PATH="$TESTBENCH/dafny"
else
    ARTIFACT_PATH="$SUT_ARTIFACT_PATH"
    DAFNY_PROJECT_PATH="$WORKSPACE/dafny"
fi

# Set the results directory (todo: categorise based on files)
RESULTS_DIRECTORY="$ARTIFACT_PATH/single-run-results/"
SEQUENTIAL_RUNSETTINGS="$(pwd)/sequential.runsettings"

test -d "$DAFNY_PROJECT_PATH"
test -f "$PARALLEL_RUNSETTINGS"

pushd "$DAFNY_PROJECT_PATH"

# Execute specified test
dotnet test --no-restore "$MAYBE_NO_BUILD_FLAG" --nologo -c Release \
--logger "console;verbosity=normal" \
--results-directory "$RESULTS_DIRECTORY" \
--settings "$SEQUENTIAL_RUNSETTINGS" \
--filter "DisplayName~$TESTCASE" \
Source/IntegrationTests

popd