#!/bin/bash

set -uex

test -f env.sh && echo "mutate-csharp-dafny/env.sh found" || { echo "mutate-csharp-dafny/env.sh not found"; exit 1; }
source env.sh

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

# Locate dafny path based on the experiment flag
if $EXPERIMENT; then
    DAFNY_PROJECT_PATH="$TESTBENCH/dafny"
else
    DAFNY_PROJECT_PATH="$WORKSPACE/dafny"
fi

pushd "$DAFNY_PROJECT_PATH"

DAFNY_INTEGRATION_TEST_PATH="$DAFNY_PROJECT_PATH/Source/IntegrationTests/TestFiles/LitTests/LitTest"
test -d "$DAFNY_INTEGRATION_TEST_PATH"

# Delete flaky integration tests 

# projectAsLibrary
rm "$DAFNY_INTEGRATION_TEST_PATH/cli/projectFile/libs/high/projectAsLibrary.dfy"
rm "$DAFNY_INTEGRATION_TEST_PATH/cli/projectFile/libs/high/projectAsLibrary.dfy.expect"

# SequenceRace
rm "$DAFNY_INTEGRATION_TEST_PATH/benchmarks/sequence-race/SequenceRace.dfy"
rm "$DAFNY_INTEGRATION_TEST_PATH/benchmarks/sequence-race/SequenceRace.dfy.expect"

# git-issues/git-issue-1514.dfy
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514.dfy"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514.dfy.expect"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514.dfy.rs.check"

# git-issues/git-issue-1514b.dfy
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514b.dfy"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514b.dfy.expect"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514b.dfy.rs.check"

# git-issues/git-issue-1514c.dfy
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514c.dfy"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514c.dfy.expect"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-1514c.dfy.rs.check"

# git-issues/git-issue-267.dfy
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-267.dfy"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-267.dfy.expect"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-267.dfy.py.check"

# git-issues/git-issue-697j.dfy
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-697j.dfy"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-697j.dfy.expect"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-697j.dfy.rs.check"
rm "$DAFNY_INTEGRATION_TEST_PATH/git-issues/git-issue-697j.dfy.verifier.expect"

# stdlibs/StandardLibraries_TargetSpecific.dfy
rm "$DAFNY_INTEGRATION_TEST_PATH/stdlibs/StandardLibraries_TargetSpecific.dfy"
rm "$DAFNY_INTEGRATION_TEST_PATH/stdlibs/StandardLibraries_TargetSpecific.dfy.cpp.check"
rm "$DAFNY_INTEGRATION_TEST_PATH/stdlibs/StandardLibraries_TargetSpecific.dfy.dfy.check"
rm "$DAFNY_INTEGRATION_TEST_PATH/stdlibs/StandardLibraries_TargetSpecific.dfy.rs.check"
rm "$DAFNY_INTEGRATION_TEST_PATH/stdlibs/StandardLibraries_TargetSpecific.dfy.expect"