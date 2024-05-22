#!/usr/bin/env bash

set -uex

test -f env.sh
test -f artifact-output.patch

source env.sh

# Find the root of the dafny project
if [ "$1" == "experiment" ]; then
    DAFNY_PROJECT_PATH="$TESTBENCH/dafny"
else
    DAFNY_PROJECT_PATH="$WORKSPACE/dafny"
fi

FILE_TO_PATCH="$DAFNY_PROJECT_PATH/Source/TestDafny/MultiBackendTest.cs"
test -f "$FILE_TO_PATCH"

pushd "$DAFNY_PROJECT_PATH"

# Apply the patch
patch "$FILE_TO_PATCH" < artifact-output.patch

popd