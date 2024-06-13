#!/bin/bash

TARGET_BACKENDS=("py" "cs" "go" "js")
DAFNY_FILE="main.dfy"
LATEST_DAFNY="/home/ubuntu/volume/workspace/dafny"
REGULAR_COMPILATION_TIMEOUT=30
REGULAR_EXECUTION_TIMEOUT=30
OVERALL_ERROR_STATUS="RUNTIME_STDOUT_DIFFER"

function conduct_interestingness_candidate_test {
  local check_for="$1"
  local first_backend="${TARGET_BACKENDS[0]}"

  case "$check_for" in
    # TODO: other conditions.
    "RUNTIME_STDOUT_DIFFER")
      # Set the baseline to compare against.
      local first_backend="${TARGET_BACKENDS[0]}"
      local differ_exit_code=1 # set to 0 if interesting

      # Check if the stdout file does not exist
        if [[ ! -e "${first_backend}_stdout.txt" ]]; then
            echo "Standard output file '${first_backend}_stdout.txt' does not exist."
        fi

        # Check if the stderr file does not exist
        if [[ ! -e "${first_backend}_stderr.txt" ]]; then
            echo "Standard error file '${first_backend}_stderr.txt' does not exist."
        fi

      for backend in "${TARGET_BACKENDS[@]:1}"; do
        # Check if the stdout file does not exist
        if [[ ! -e "${backend}_stdout.txt" ]]; then
            echo "Standard output file '${backend}_stdout.txt' does not exist."
        fi

        # Check if the stderr file does not exist
        if [[ ! -e "${backend}_stderr.txt" ]]; then
            echo "Standard error file '${backend}_stderr.txt' does not exist."
        fi

        # Compare output.
        local DIFF
        DIFF=$(diff "${first_backend}_stdout.txt" "${backend}_stdout.txt")
        if [[ -n "$DIFF" && "$DIFF" == *"false"* && "$DIFF" == *"true"* ]]; then
          differ_exit_code=0
          rm "${backend}_stdout.txt"
        fi
      done
      rm "${first_backend}_stdout.txt"
      exit $differ_exit_code
      ;;
    *)
      exit 1 # case not supported.
      ;;
  esac
}

function compile_candidate_program {
  local target="$1"
  compile_command=("dotnet" "$LATEST_DAFNY/Binaries/Dafny.dll" "build" "--no-verify" "--allow-warnings" \
   "--target:$target" "$DAFNY_FILE")
  echo "Compiling program against $target with command: " "${compile_command[@]}"
  timeout $REGULAR_COMPILATION_TIMEOUT "${compile_command[@]}"
  local exit_code="$?"

  # Check if the compilation exit code is non-zero.
  if [[ $exit_code -eq 124 ]]; then
    echo "Compilation for ${target} timed out."
    exit 124 # exit 0 if we want to find timeout interesting
  elif [[ $exit_code -ne 0 ]]; then
    echo "Compilation for ${target} failed with exit code $exit_code."
    exit $exit_code # exit 0 if we want to find crashes interesting
  else
    echo "Compilation succeeded for ${target}."
  fi
}

function run_candidate_program_command {
  local target="$1"
  local filename="${DAFNY_FILE%.*}"

  case "$target" in
    "py") echo "python3 $filename-py/__${filename}__.py" ;;
    "cs") echo "dotnet $filename.dll" ;;
    "go") echo "./$filename" ;;
    "js") echo "node $filename.js" ;;
    *) echo "target $target not supported! check reduction setup."; exit 1 ;;
  esac
}

# Results are stored in {target}_stdout.txt / {target_stderr}.txt.
# For now, we error if exit code is non-zero.
function run_candidate_program {
  local target="$1"
  local run_command
  run_command=$(run_candidate_program_command "$target")
  echo "Executing program against $target with command: " "${run_command}"

  timeout $REGULAR_EXECUTION_TIMEOUT bash -c "$run_command" > "${target}_stdout.txt" 2> "${target}_stderr.txt"
  local exit_code="$?"

  # Check if the stdout file does not exist
  if [[ ! -e "${target}_stdout.txt" ]]; then
      echo "Standard output file '${target}_stdout.txt' does not exist."
  fi

  # Check if the stderr file does not exist
  if [[ ! -e "${target}_stderr.txt" ]]; then
      echo "Standard error file '${target}_stderr.txt' does not exist."
  fi

  # Check if the exit code is non-zero.
  if [[ $exit_code -eq 124 ]]; then
    echo "Execution for ${target} timed out."
    exit 124
  #   exit_code=0  # Reset to 0 since timeout is interesting in itself.
  elif [[ $exit_code -ne 0 ]]; then
    echo "Execution for ${target} failed with exit code $exit_code."
    exit $exit_code
  else
    echo "Execution succeeded for ${target}."
  fi
}

# Sanity checks. (target backends should have at least 1)
if [[ "${#TARGET_BACKENDS[@]}" -le 1 ]]; then
  exit 1 # Unable to conduct differential testing.
fi

# 0) Install bignumber.js (dependency.)
 npm install bignumber.js

 # 1) Validate program compiles with the Dafny compiler built from the latest commit
 for target_backend in "${TARGET_BACKENDS[@]}"; do
   compile_candidate_program "$target_backend"
 done

 # 2) Run the program compiled by the Dafny compiler built from the latest commit
 for target_backend in "${TARGET_BACKENDS[@]}"; do
   run_candidate_program "$target_backend"
 done

# 3) Check for interestingness condition. (miscompilation)
conduct_interestingness_candidate_test "$OVERALL_ERROR_STATUS"

# Sanity checks.
echo "Execution slipped through interesting-ness check: this should not happen!"
exit 1