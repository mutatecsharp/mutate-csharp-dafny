#!/bin/bash

set -uex

test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
source env.sh

EXPERIMENT=false

while getopts "eh" opt; do
    case $opt in
        e)
            EXPERIMENT=true
            ;;
        h)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

TESTCASE=$1

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
PARALLEL_RUNSETTINGS="$(pwd)/parallel.runsettings"

test -d "$DAFNY_PROJECT_PATH"
test -f "$PARALLEL_RUNSETTINGS"

pushd "$DAFNY_PROJECT_PATH"

# Execute specified test
dotnet test --no-restore -c Release --logger "console;verbosity=normal" \
--results-directory "$RESULTS_DIRECTORY" \
--settings "$PARALLEL_RUNSETTINGS" \
--filter "DisplayName~$TESTCASE" \
Source/IntegrationTests

popd