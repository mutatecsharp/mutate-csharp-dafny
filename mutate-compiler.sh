#!/bin/bash

set -uex

DRY_RUN=""
MAYBE_NO_BUILD_FLAG=""

usage() {
    echo "Script to mutate the Dafny compiler."
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
DAFNY_PROJECT_PATH="$MUTATED_DAFNY_ROOT"

test -d "$MUTATE_CSHARP_PATH"
test -d "$DAFNY_PROJECT_PATH"

# Build mutate-csharp
pushd $MUTATE_CSHARP_PATH
test $MAYBE_NO_BUILD_FLAG || dotnet build -c Release MutateCSharp.sln
popd

test -x "$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp"

# Mutate dafny
$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp \
mutate --omit-redundant "$DRY_RUN" \
--project "$DAFNY_PROJECT_PATH/Source/DafnyCore/DafnyCore.csproj" \
--directories "$DAFNY_PROJECT_PATH/Source/DafnyCore/Backends" \
--ignore-files "$DAFNY_PROJECT_PATH/Source/DafnyCore/Parser.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/Scanner.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/Generic/SccGraph.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/Generic/Stringify.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/Generic/GenericErrors.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/AST/Grammar/SourcePreprocessor.cs"
