#!/usr/bin/env bash

set -uex

# Set the path to the dafny project path that is under test
VOLUME_ROOT=$(realpath "")
WORKSPACE="$VOLUME_ROOT/workspace"
TESTBENCH="$VOLUME_ROOT/testbench"

WORKSPACE_MUTATE_CSHARP_ROOT="$WORKSPACE/mutate-csharp"

SUT_ARTIFACT_PATH="$WORKSPACE/artifact/testartifacts"
EXPERIMENT_ARTIFACT_PATH="$TESTBENCH/artifact/testartifacts"

SUT_DAFNY_ROOT="$WORKSPACE/dafny"

test -d "$MUTATE_CSHARP_ROOT"
test -d "$SUT_DAFNY_ROOT"

export VOLUME_ROOT
export WORKSPACE
export TESTBENCH
export SUT_DAFNY_ROOT
export SUT_ARTIFACT_PATH
export EXPERIMENT_ARTIFACT_PATH
export WORKSPACE_MUTATE_CSHARP_ROOT