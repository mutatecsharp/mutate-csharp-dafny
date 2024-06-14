#!/usr/bin/env python3.11
import argparse
import os
import shlex
import random
import subprocess

from itertools import chain
from loguru import logger
from pathlib import Path
from fuzzing.util.mutation_registry import MutationRegistry


def validate_volume_directory_exists():
    volume_dir = os.environ.get('VOLUME_ROOT')
    return volume_dir and os.path.exists(volume_dir)


def obtain_env_vars():
    # Sanity check: we should be in mutate-csharp-dafny directory
    if not os.path.exists('env.sh') or not os.path.exists('parallel.runsettings'):
        logger.error('Please run this script from the root of the mutate-csharp-dafny directory.')
        exit(1)

    env_dict = {}

    # Source env.sh and print environment variables
    command = shlex.split("bash -c 'source env.sh && env'")
    proc = subprocess.Popen(command, stdout=subprocess.PIPE)
    for line in proc.stdout:
        decoded_line = line.decode('utf-8').strip()
        (key, _, value) = decoded_line.partition("=")
        env_dict[key] = value
    proc.communicate()

    return env_dict


def validated_mutant_registry(mutation_registry_path: Path, tracer_registry_path: Path):
    if mutation_registry_path.name != "registry.mucs.json" or tracer_registry_path.name != "tracer-registry.mucs.json":
        logger.error("Invalid mutation/tracer registry path.")
        exit(1)

    mutation_registry = MutationRegistry.reconstruct_from_disk(mutation_registry_path)
    tracer_registry = MutationRegistry.reconstruct_from_disk(tracer_registry_path)
    logger.info(f"Files mutated: {len(mutation_registry.file_relative_path_to_registry)}")

    # Sanity checks
    assert len(mutation_registry.file_relative_path_to_registry) == len(tracer_registry.file_relative_path_to_registry)
    assert set(mutation_registry.file_relative_path_to_registry.keys()) == set(
        tracer_registry.file_relative_path_to_registry.keys())
    assert set(mutation_registry.env_var_to_registry.keys()) == set(tracer_registry.env_var_to_registry.keys())
    for file_env_var in mutation_registry.env_var_to_registry.keys():
        assert len(mutation_registry.get_file_registry(file_env_var).mutations) == \
               len(tracer_registry.get_file_registry(file_env_var).mutations)
        for mutation in mutation_registry.get_file_registry(file_env_var).mutations.keys():
            assert mutation in tracer_registry.get_file_registry(file_env_var).mutations

    return mutation_registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutation_registry", type=Path, required=True)
    parser.add_argument("--tracer_registry", type=Path, required=True)
    parser.add_argument("--sample_size", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.mutation_registry.exists() or not args.tracer_registry.exists():
        logger.error("Invalid mutation/tracer registry path.")
        exit(1)

    mutation_registry = validated_mutant_registry(args.mutation_registry, args.tracer_registry)

    # random sample x number of mutants
    all_mutants = chain.from_iterable([[(env_var, mutant_id) for mutant_id, _ in registry.mutations.items()] for (env_var, registry) in
                         mutation_registry.env_var_to_registry.items()])
    all_mutants = list(all_mutants)
    logger.info("mutant count: {}", len(all_mutants))

    if args.sample_size > len(all_mutants):
        logger.error("Invalid sample size ({} out of {}).", args.sample_size, len(all_mutants))
        exit(1)

    sampled_mutants = random.sample(all_mutants, args.sample_size)

    output_path : Path = args.output
    with output_path.open('w') as f:
        for (env_var, mutant_id) in sampled_mutants:
            f.write(f"{env_var}:{mutant_id}\n")


if __name__ == '__main__':
    main()
