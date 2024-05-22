#!/bin/bash

set -uex

# Should source the env.sh file in mutate-csharp project before running this script
test -f env.sh
source env.sh

# Set the artifact path
if [ -n "$1" ] && [ "$1" == "experiment" ]; then
    ARTIFACT_PATH="$EXPERIMENT_ARTIFACT_PATH"
    DAFNY_PROJECT_PATH="$TESTBENCH/dafny"
    PATCH_FILE="$WORKSPACE/experiment-artifact-output.patch"
else
    ARTIFACT_PATH="$SUT_ARTIFACT_PATH"
    DAFNY_PROJECT_PATH="$WORKSPACE/dafny"
    PATCH_FILE="$WORKSPACE/sut-artifact-output.patch"
fi

echo "Artifact path: $ARTIFACT_PATH"
echo "Dafny project path: $DAFNY_PROJECT_PATH"

test -d "$ARTIFACT_PATH"
test -d "$DAFNY_PROJECT_PATH"

# Find the file to be patched
FILE_TO_PATCH="$DAFNY_PROJECT_PATH/Source/TestDafny/MultiBackendTest.cs"

echo "Output test artifact to: $ARTIFACT_PATH"
echo "Generating patch..."

LINE_NUMBER=349
NEW_LINE_CONTENT="    var tempOutputDirectory = Path.Combine($ARTIFACT_PATH, randomName, randomName);"

# Create a temporary copy of the file
TEMP_FILE=$(mktemp)
cp "$FILE_TO_PATCH" "$TEMP_FILE"

# Modify the line in the temporary file
sed "${LINE_NUMBER}s/.*/$NEW_LINE_CONTENT/" "$TEMP_FILE" > "$TEMP_FILE.modified"

# Generate the patch file
diff -u "$FILE_TO_PATCH" "$TEMP_FILE.modified" > "$PATCH_FILE"

# Clean up temporary files
rm "$TEMP_FILE" "$TEMP_FILE.modified"

echo "Patch file created: $PATCH_FILE"