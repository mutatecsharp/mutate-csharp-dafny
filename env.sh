#!/usr/bin/env bash

set -uex

# Set the path to the dafny project path that is under test
# Volume root should be set
test -d "$VOLUME_ROOT"

REGULAR_ROOT="$VOLUME_ROOT/original"
MUTATED_ROOT="$VOLUME_ROOT/workspace"
TRACED_ROOT="$VOLUME_ROOT/testbench"

WORKSPACE_MUTATE_CSHARP_ROOT="$MUTATED_ROOT/mutate-csharp"
MUTATE_DAFNY_RECORDS_ROOT="$VOLUME_ROOT/mutate-dafny-records"

MUTATED_ARTIFACT_PATH="$MUTATED_ROOT/testartifact"
TRACED_ARTIFACT_PATH="$TRACED_ROOT/testartifact"

REGULAR_DAFNY_ROOT="$REGULAR_ROOT/dafny"
MUTATED_DAFNY_ROOT="$MUTATED_ROOT/dafny"
TRACED_DAFNY_ROOT="$TRACED_ROOT/dafny"

test -d "$WORKSPACE_MUTATE_CSHARP_ROOT"
test -d "$MUTATED_DAFNY_ROOT"
test -d "$TRACED_DAFNY_ROOT"
test -d "$REGULAR_DAFNY_ROOT"

echo "mutate-dafny-records directory: $MUTATE_DAFNY_RECORDS_ROOT"
echo "mutate-csharp directory: $WORKSPACE_MUTATE_CSHARP_ROOT"
echo "mutated Dafny directory: $MUTATED_DAFNY_ROOT"
echo "traced Dafny directory: $TRACED_DAFNY_ROOT"
echo "regular Dafny directory: $REGULAR_DAFNY_ROOT"

test -f dependency_env.sh && echo "dependency_env.sh found" || { echo "mutate-csharp-dafny/dependency_env.sh not found"; exit 1; }
source dependency_env.sh

# mutate-csharp setup paths
export VOLUME_ROOT
export WORKSPACE
export TESTBENCH
export REGULAR_DAFNY_ROOT
export MUTATED_DAFNY_ROOT
export TRACED_DAFNY_ROOT
export MUTATED_ARTIFACT_PATH
export TRACED_ARTIFACT_PATH
export WORKSPACE_MUTATE_CSHARP_ROOT
export MUTATE_DAFNY_RECORDS_ROOT

# upstream dependencies
export JAVA_19_BINARY_PATH