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
    esac
done
shift $((OPTIND-1))

test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
test -f parallel.runsettings && echo "mutate-csharp-dafny/parallel.runsettings found" || { echo "mutate-csharp-dafny/parallel.runsettings not found"; exit 1; }
source env.sh
test -f allow-mutation-env-var.py

MUTATE_CSHARP_PATH="$WORKSPACE_MUTATE_CSHARP_ROOT"

test -d "$MUTATE_CSHARP_PATH"

INTEGRATION_TEST_PATH="$MUTATED_DAFNY_ROOT/Source/IntegrationTests"

test -d "$INTEGRATION_TEST_PATH"

# Apply patch to overwrite artifact output
./overwrite-artifact-output.sh

# Apply patch to whitelist mutate-csharp environment variable
./allow-mutation-env-var.py --registry-path "$MUTATED_DAFNY_ROOT/Source/DafnyCore/registry.mucs.json"

# Build mutate-csharp
pushd $MUTATE_CSHARP_PATH
dotnet build -c Release MutateCSharp.sln
popd

test -x "$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp"

# Run mutation testing on dafny # --source-file-under-test  \
$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp \
test \
--test-project "$INTEGRATION_TEST_PATH/IntegrationTests.csproj" \
--project "$MUTATED_DAFNY_ROOT/Source/DafnyCore/DafnyCore.csproj" \
--passing-tests "$MUTATE_DAFNY_RECORDS_ROOT/passing-tests.txt" \
--mutation-registry "$MUTATED_DAFNY_ROOT/Source/DafnyCore/registry.mucs.json" \
--tracer-registry "$TRACED_DAFNY_ROOT/Source/DafnyCore/tracer-registry.mucs.json" \
--mutant-traces "$TRACED_ARTIFACT_PATH/execution-trace" \
--testrun-settings "$(pwd)/basic.runsettings" \
--temporary-directory "$MUTATED_ARTIFACT_PATH/compilations" \
"$DRY_RUN"