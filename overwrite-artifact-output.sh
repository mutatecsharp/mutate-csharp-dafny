#!/bin/bash

set -uex

test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
source env.sh

# Get options to determine if we want to generate patch for experiments or SUT
usage() {
    echo "Usage: $0 [-e]"
    exit 1
}

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

# Set the artifact path
if $EXPERIMENT; then
    COMPILED_ARTIFACT_PATH="$EXPERIMENT_ARTIFACT_PATH/compilations"
    DAFNY_PROJECT_PATH="$TESTBENCH/dafny"
    PATCH_FILE="$WORKSPACE/experiment-artifact-output.patch"
else
    COMPILED_ARTIFACT_PATH="$SUT_ARTIFACT_PATH/compilations"
    DAFNY_PROJECT_PATH="$WORKSPACE/dafny"
    PATCH_FILE="$WORKSPACE/sut-artifact-output.patch"
fi

test -d "$DAFNY_PROJECT_PATH"

# Find the file to be patched
FILE_TO_PATCH="$DAFNY_PROJECT_PATH/Source/TestDafny/MultiBackendTest.cs"

echo "Output test compilations to: $COMPILED_ARTIFACT_PATH"

LINE_NUMBER=349
NEW_LINE_CONTENT="    var tempOutputDirectory = Path.Combine(\"$COMPILED_ARTIFACT_PATH\", randomName, randomName);"

# Modify the line in the temporary file in-place
sed -i "${LINE_NUMBER}s|.*|$NEW_LINE_CONTENT|" "$FILE_TO_PATCH"

echo "Overwritten artifact output in-place."