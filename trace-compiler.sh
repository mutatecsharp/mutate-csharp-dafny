#!/bin/bash

set -uex

usage() {
    echo "Script to trace the Dafny compiler mutant execution."
}

while getopts "hd" opt; do
    case $opt in
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

MUTATE_CSHARP_PATH="$WORKSPACE_MUTATE_CSHARP_ROOT"
PASSING_TESTS_PATH="$MUTATE_DAFNY_RECORDS_ROOT/passing-tests.txt"

test -d "$MUTATE_CSHARP_PATH"
test -d "$MUTATED_DAFNY_ROOT"
test -d "$TRACED_DAFNY_ROOT"
test "$TRACED_ARTIFACT_PATH"
test -f "$PASSING_TESTS_PATH"

# Build mutate-csharp
pushd $MUTATE_CSHARP_PATH
dotnet build -c Release MutateCSharp.sln
popd

test -x "$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp"

# Apply patch to overwrite artifact output
./overwrite-artifact-output.sh -e

# Apply patch to whitelist mutate-csharp environment variable
./allow-tracer-env-var.py --registry-path "$TRACED_DAFNY_ROOT/Source/DafnyCore/tracer-registry.mucs.json"

# trace dafny
$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp \
trace \
--test-project "$TRACED_DAFNY_ROOT/Source/IntegrationTests" \
--output-directory "$TRACED_ARTIFACT_PATH/execution-trace" \
--tests-list "$PASSING_TESTS_PATH" \
--mutation-registry "$MUTATED_DAFNY_ROOT/Source/DafnyCore/registry.mucs.json" \
--tracer-registry "$TRACED_DAFNY_ROOT/Source/DafnyCore/tracer-registry.mucs.json" \
--testrun-settings "$(pwd)/basic.runsettings"

# Delete compilation artifacts
rm -rf "$TRACED_ARTIFACT_PATH/compilations"