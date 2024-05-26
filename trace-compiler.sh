#!/bin/bash

set -uex

DRY_RUN=""
MAYBE_NO_BUILD_FLAG=""

usage() {
    echo "Script to trace the Dafny compiler mutant execution."
    echo "Usage: $0 [-n]"
    echo
    echo "Options:"
    echo "  -n           Do not build Dafny."
}

while getopts "nhd" opt; do
    case $opt in
        n)
            MAYBE_NO_BUILD_FLAG="--no-build"
            ;;
        d)
            DRY_RUN="--dry-run"
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

# Locate dafny path
MUTATE_CSHARP_PATH="$WORKSPACE_MUTATE_CSHARP_ROOT"
DAFNY_PROJECT_PATH="$WORKSPACE/dafny"

test -d "$MUTATE_CSHARP_PATH"
test -d "$DAFNY_PROJECT_PATH"
test "$SUT_ARTIFACT_PATH"

# Build mutate-csharp
pushd $MUTATE_CSHARP_PATH
test $MAYBE_NO_BUILD_FLAG || dotnet build -c Release MutateCSharp.sln
popd

test -x "$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp"

# Mutate dafny
$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp \
trace \
--test-project "$DAFNY_PROJECT_PATH/Source/IntegrationTests" \
--output-directory "$SUT_ARTIFACT_PATH/execution-trace" \
--tests-list "$SUT_ARTIFACT_PATH/execution-trace/tests-list.txt" \
--mutation-registry "$DAFNY_PROJECT_PATH/Source/DafnyCore/registry.mucs.json" \
--tracer-registry "$DAFNY_PROJECT_PATH/Source/DafnyCore/tracer-registry.mucs.json" \
--testrun-settings "$(pwd)/basic.runsettings"

