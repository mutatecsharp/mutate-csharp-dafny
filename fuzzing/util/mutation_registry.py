import json

from pathlib import Path


class MutationRegistry:
    def __init__(self, raw_json):
        self.file_relative_path_to_registry = {relative_path: FileMutationRegistry(registry_json) for
                                               relative_path, registry_json in raw_json.items()}

    @staticmethod
    def reconstruct_from_disk(path: Path):
        if not path.exists():
            print("Mutation registry does not exist.")
            exit(1)

        with path.open(mode='r') as f:
            registry_json = json.load(f)

        return MutationRegistry(registry_json)


class FileMutationRegistry:
    def __init__(self, raw_json):
        self.relative_path = raw_json['FileRelativePath']
        self.env_var = raw_json['EnvironmentVariable']
        self.mutations = {mutant_id: Mutation(mutation_json) for mutant_id, mutation_json in
                          raw_json['Mutations'].items()}


class Mutation:
    def __init__(self, raw_json):
        self.id = raw_json['MutantId']
        self.original_operation = raw_json['OriginalOperation']
        self.original_template = raw_json['OriginalExpressionTemplate']
        self.mutant_operation = raw_json['MutantOperation']
        self.mutant_operand_kind = raw_json['MutantOperandKind']
        self.mutant_template = raw_json['MutantExpressionTemplate']
        self.source_span = raw_json['SourceSpan']
        self.line_span = raw_json['LineSpan']
