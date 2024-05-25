#!/bin/bash

set -uex

EXPERIMENT=false
MAYBE_NO_BUILD_FLAG=""

usage() {
    echo "Script to mutate the Dafny compiler."
    echo "Usage: $0 [-n]"
    echo
    echo "Options:"
    echo "  -n           Do not build Dafny."
}

while getopts "nh" opt; do
    case $opt in
        n)
            MAYBE_NO_BUILD_FLAG="--no-build"
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
ARTIFACT_PATH="$SUT_ARTIFACT_PATH"
DAFNY_PROJECT_PATH="$WORKSPACE/dafny"

test -d "$MUTATE_CSHARP_PATH"
test -d "$ARTIFACT_PATH"
test -d "$DAFNY_PROJECT_PATH"

# Mutate dafny
.$MUTATE_CSHARP_PATH/bin/Release/net8.0/MutateCSharp \
mutate --omit-redundant \
--project "$DAFNY_PROJECT_PATH/Source/DafnyCore/DafnyCore.csproj" \
--directories "$DAFNY_PROJECT_PATH/Source/DafnyCore/Backends" \
--ignore-files /mnt/volume_lon1_02/workspace/dafny/Source/DafnyCore/Parser.cs \
/mnt/volume_lon1_02/workspace/dafny/Source/DafnyCore/Scanner.cs \
/mnt/volume_lon1_02/workspace/dafny/Source/DafnyCore/Generic/SccGraph.cs \
/mnt/volume_lon1_02/workspace/dafny/Source/DafnyCore/Generic/Stringify.cs \
/mnt/volume_lon1_02/workspace/dafny/Source/DafnyCore/Generic/GenericErrors.cs \
/mnt/volume_lon1_02/workspace/dafny/Source/DafnyCore/AST/Grammar/SourcePreprocessor.cs
