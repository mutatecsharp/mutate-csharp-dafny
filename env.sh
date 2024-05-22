#!/usr/bin/env bash

set -uex

# Set the path to the dafny project path that is under test
# Volume root should be set
test -d "$VOLUME_ROOT"



WORKSPACE="$VOLUME_ROOT/workspace"
TESTBENCH="$VOLUME_ROOT/testbench"

WORKSPACE_MUTATE_CSHARP_ROOT="$WORKSPACE/mutate-csharp"

SUT_ARTIFACT_PATH="$WORKSPACE/testartifact"
EXPERIMENT_ARTIFACT_PATH="$TESTBENCH/testartifact"

SUT_DAFNY_ROOT="$WORKSPACE/dafny"

test -d "$WORKSPACE_MUTATE_CSHARP_ROOT"
test -d "$SUT_DAFNY_ROOT"

echo "mutate-csharp directory: $WORKSPACE_MUTATE_CSHARP_ROOT"
echo "SUT Dafny directory: $SUT_DAFNY_ROOT"

export VOLUME_ROOT
export WORKSPACE
export TESTBENCH
export SUT_DAFNY_ROOT
export SUT_ARTIFACT_PATH
export EXPERIMENT_ARTIFACT_PATH
export WORKSPACE_MUTATE_CSHARP_ROOT