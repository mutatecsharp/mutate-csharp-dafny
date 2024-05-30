#!/bin/bash

set -uex

usage() {
    echo "Script to generate mutant execution tracer for the Dafny compiler."
}

TARGET_TRACER=false

while getopts "eh" opt; do
    case $opt in
        e)
            TARGET_TRACER=true
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

MUTATE_CSHARP_PATH="$WORKSPACE_MUTATE_CSHARP_ROOT"

# Locate dafny path based on the experiment flag
if $TARGET_TRACER; then
    DAFNY_PROJECT_PATH="$TRACED_DAFNY_ROOT"
else
    DAFNY_PROJECT_PATH="$MUTATED_DAFNY_ROOT"
fi

test -d "$MUTATE_CSHARP_PATH"
test -d "$DAFNY_PROJECT_PATH"

# Build mutate-csharp
pushd $MUTATE_CSHARP_PATH
dotnet build -c Release MutateCSharp.sln
popd

test -x "$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp"

# Mutate dafny
$MUTATE_CSHARP_PATH/artifacts/MutateCSharp/bin/Release/net8.0/MutateCSharp \
generate-tracer --omit-redundant \
--project "$DAFNY_PROJECT_PATH/Source/DafnyCore/DafnyCore.csproj" \
--directories "$DAFNY_PROJECT_PATH/Source/DafnyCore/GeneratedFromDafny" \
--ignore-files "$DAFNY_PROJECT_PATH/Source/DafnyCore/Parser.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/Scanner.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/Generic/SccGraph.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/Generic/Stringify.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/Generic/GenericErrors.cs" \
"$DAFNY_PROJECT_PATH/Source/DafnyCore/AST/Grammar/SourcePreprocessor.cs"
