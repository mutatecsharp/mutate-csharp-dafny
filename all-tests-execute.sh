#!/bin/bash

set -uex

echo "$(pwd)"

# Should source the env.sh file in mutate-csharp project before running this script
test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
test -f parallel.runsettings && echo "mutate-csharp-dafny/parallel.runsettings found" || { echo "mutate-csharp-dafny/parallel.runsettings not found"; exit 1; }
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
RESULTS_DIRECTORY="$ARTIFACT_PATH/results/"

test -d "$DAFNY_PROJECT_PATH"

pushd "$DAFNY_PROJECT_PATH"

# Execute all tests (stop when first test fails)
dotnet test --no-restore -c Release --logger "console;verbosity=normal" \
--results-directory "$RESULTS_DIRECTORY/firstrun" \
--settings "$(pwd)/parallel.runsettings" \
Source/IntegrationTests

popd