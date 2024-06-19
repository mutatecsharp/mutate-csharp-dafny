# mutate-csharp-dafny: an application of mutation testing on compilers

As  `mutate-csharp-dafny` applies mutation analysis to _automatically_ generate test cases for the Dafny compiler,
and integrates the workflow with existing fuzzing techniques to also simultaneously (and automatically) discover bugs
in the Dafny compiler.

## Features

- Fuzzing: `mutate-csharp-dafny` uses a third-party fuzzer (fuzz-d) to generate random programs in Dafny, which is used to
apply differential testing on the Dafny compiler backends.
- Non-redundant test case generation: if differential testing on a randomly generated program passes the checks,
`mutate-csharp-dafny` fuzzes mutants that are undetected by the Dafny regression test suite with the same program,
and persists the program as a test case candidate to a specified directory if the compiler crashes or miscompiles given the input.
- Program reduction: `mutate-csharp-dafny` uses a third-party program reducer (PERSES) to shrink programs into a debuggable program
that can be submitted to the compiler developers.
- TRX parser: `.trx` is a custom test result format that inherits XML syntax used by the .NET test framework. This can be used
to sort test cases by execution time.
- Test name extractor: When applying `dotnet --list-tests` option, the same list cannot be trivially fed back to the .NET `test` command.
This escapes the characters necessary to allow the test frameworks to recognise the tests by its name.
- Random mutant sampler: Given the mutation registry, randomly sample a specified number of mutants for mutation analysis.
- Examples: `mutate-csharp-dafny` hosts a variety of scripts that showcase how `mutate-csharp` can be utilised to apply mutation analysis
on a program under test.

## Getting started

### Cloning repository

To clone `mutate-csharp-dafny`, run: 
```sh
git clone --recursive git@github.com:mutatecsharp/mutate-csharp-dafny.git
```

### Dependencies

#### TL;DR
```sh
apt install python3.11
alias python=python3.11
python -m pip install loguru
```
Install [dependencies](https://github.com/fuzz-d/fuzz-d) for fuzz-d.

Install [dependencies](https://github.com/fuzz-d/perses) for PERSES.

#### Further details

`mutate-csharp-dafny` is supported on Ubuntu 20.04.
At the time of writing, the Dafny compiler is tested with `python3.11`.

`mutate-csharp-dafny` logs all actions run by the driver using `loguru`. To install `loguru`, run:
```sh
python -m pip install loguru
```

## Usage

`mutate-csharp-dafny` is designed such that all scripts are run within the root directory of `mutate-csharp-dafny`.
`mutate-csharp-dafny` requires that all cloned repositories involving `mutate-csharp` to be within a volume directory,
which can be set with:
```sh
export VOLUME_ROOT= {{ folder containing mutate-csharp-dafny }}
```

For the python scripts, prefix the execution with:
```sh
PYTHONPATH=$(pwd) ...
```
where the current directory is the root of `mutate-csharp-dafny`.

### Fuzzing

```sh
PYTHONPATH=$(pwd) ./fuzzing/run-fuzzer-campaign.py --help
usage: run-fuzzer-campaign.py [-h] [--dry-run] [--seed SEED] [--fuzz_d FUZZ_D] [--dafny DAFNY]
                              [--mutated_dafny MUTATED_DAFNY] [--traced_dafny TRACED_DAFNY]
                              --output_directory OUTPUT_DIRECTORY [--mutation_registry MUTATION_REGISTRY]
                              [--tracer_registry TRACER_REGISTRY] [--passing_tests PASSING_TESTS]
                              [--regression_test_trace_dir REGRESSION_TEST_TRACE_DIR]
                              [--mutation_test_result MUTATION_TEST_RESULT [MUTATION_TEST_RESULT ...]]
                              [--source_file_relative_path SOURCE_FILE_RELATIVE_PATH [SOURCE_FILE_RELATIVE_PATH ...]]
                              [--compilation_timeout COMPILATION_TIMEOUT]
                              [--generation_timeout GENERATION_TIMEOUT]
                              [--execution_timeout EXECUTION_TIMEOUT]
                              [--test_campaign_timeout TEST_CAMPAIGN_TIMEOUT]

options:
  -h, --help            show this help message and exit
  --dry-run             Perform dry run.
  --seed SEED           Optional. Seed for random number generator. Useful to reproduce results.
  --fuzz_d FUZZ_D       Path to the fuzz-d project.
  --dafny DAFNY         Path to the non-mutated Dafny project.
  --mutated_dafny MUTATED_DAFNY
                        Path to the mutated Dafny project.
  --traced_dafny TRACED_DAFNY
                        Path to the execution-trace instrumented Dafny project.
  --output_directory OUTPUT_DIRECTORY
                        Path to the persisted/temporary interesting programs output directory.
  --mutation_registry MUTATION_REGISTRY
                        Path to registry generated after mutating the Dafny codebase (.json).
  --tracer_registry TRACER_REGISTRY
                        Path to registry generated after instrumenting the Dafny codebase to trace mutant
                        executions (.json).
  --passing_tests PASSING_TESTS
                        Path to file containing lists of passing tests.
  --regression_test_trace_dir REGRESSION_TEST_TRACE_DIR
                        Path to directory containing all mutant execution traces after running the Dafny
                        regression test suite.
  --mutation_test_result MUTATION_TEST_RESULT [MUTATION_TEST_RESULT ...]
                        Path to mutation analysis result(s) of the Dafny regression test suite (.json). The
                        analysis results will be merged if multiple results are passed.
  --source_file_relative_path SOURCE_FILE_RELATIVE_PATH [SOURCE_FILE_RELATIVE_PATH ...]
                        Optional. If specified, only consider mutants for the specified file(s).
  --compilation_timeout COMPILATION_TIMEOUT
                        Maximum second(s) allowed to compile generated program with the non-mutated Dafny
                        compiler.
  --generation_timeout GENERATION_TIMEOUT
                        Maximum second(s) allowed to generate program with fuzz-d.
  --execution_timeout EXECUTION_TIMEOUT
                        Maximum second(s) allowed to execute fuzz-d generated program compiled by the non-
                        mutated Dafny compiler.
  --test_campaign_timeout TEST_CAMPAIGN_TIMEOUT
                        Test campaign time budget in hour(s).
```

### Shrink Dafny programs
The `reduce-regular-program.sh` is an interestingness test script example and should be modified to suit the 
conditions required to shrink the program.


### Apply escape characters to test names

```sh
PYTHONPATH=$(pwd) ./parse-tests.py --help
usage: parse-tests.py [-h] --framework FRAMEWORK --passing-tests PASSING_TESTS

options:
  -h, --help            show this help message and exit
  --framework FRAMEWORK
                        Test target framework. Supports: nunit, mstest.
  --passing-tests PASSING_TESTS
                        Path to list of names of passing tests.
```

### Scripts using `mutate-csharp`

```sh
./mutate-compiler.sh
./generate-tracer.sh
./trace-compiler.sh
./trace-single-test.sh
./run-mutation-testing.sh
```

### Scripts related to the Dafny compiler
- `overwrite-artifact-output.sh`: Redirects all output from temporary directory to a specified directory.
- `auto-delete-compilations.py`: Watches the specified directory and deletes all compilation artifacts that are over the maximum time limit that a test/mutant combination can be assessed.
- `fuzz-tests.sh`: Runs the combined fuzzing / test generation workflow.
-  `allow-mutation-env-var.py` / `allow-tracer-env-var.py`: Whitelist the specific mutation file ID environment variables based on the mutation registry.
