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


