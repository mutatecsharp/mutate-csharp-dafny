#!/usr/bin/env bash

set -uex

JAVA_19_BINARY_PATH="/usr/lib/jvm/java-19-amazon-corretto/bin/java"

test -f "$JAVA_19_BINARY_PATH"

echo "java 19 found: $JAVA_19_BINARY_PATH"

export JAVA_19_BINARY_PATH
