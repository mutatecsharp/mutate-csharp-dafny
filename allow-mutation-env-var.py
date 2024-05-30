#! /usr/bin/env python3.11

import re
import os
import json
import shlex
import argparse
import subprocess

def validate_volume_directory_exists():
    volume_dir = os.environ.get('VOLUME_ROOT')
    return volume_dir and os.path.exists(volume_dir)


def obtain_env_vars():
    # Sanity check: we should be in mutate-csharp-dafny directory
    if not os.path.exists('env.sh') or not os.path.exists('parallel.runsettings'):
        print('Please run this script from the root of the mutate-csharp-dafny directory.')
        exit(1)
        
    env_dict = {}
        
    # Source env.sh and print environment variables
    command = shlex.split("bash -c 'source env.sh && env'")
    proc = subprocess.Popen(command, stdout = subprocess.PIPE)
    for line in proc.stdout:
        decoded_line = line.decode('utf-8').strip()
        (key, _, value) = decoded_line.partition("=")
        env_dict[key] = value
    proc.communicate()
    
    return env_dict

def get_mutated_file_count(registry_path: str):
    max_env_var = 0
    pattern = r'\d+$'
    
    with open(registry_path) as f:
        registry = json.load(f)
        
    for value in registry.values():
        print(value["EnvironmentVariable"])
        match = re.search(pattern, value["EnvironmentVariable"])
        if match:
            max_env_var = max(max_env_var, int(match.group()))
        
    return max_env_var

def replace_line(line_number: int, file_path: str, new_line: str):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return 1
    
    command = ["sed", "-i", f"{line_number}s|.*|{new_line}|", file_path]
    print(f"Running command: {' '.join(command)}")
    result = subprocess.run(command)
    return result.returncode
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", action="store_true", help="Run on traced dafny.")
    parser.add_argument("--dry-run", action="store_true", help="Dry run.")
    parser.add_argument("--registry-path", type=str, help="Path to the registry file (.json).")
    
    args = parser.parse_args()
    
    if not validate_volume_directory_exists():
        print('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)
        
    if not args.registry_path:
        print("Please provide the path to the registry file.")
        exit(1)
        
    env = obtain_env_vars()
        
    # Locate dafny path based on the experiment flag
    if args.e:
        print("Running on traced dafny codebase.")
        dafny_path = env["TRACED_DAFNY_ROOT"]
    else:
        print("Running on mutated dafny codebase.")
        dafny_path = env["MUTATED_DAFNY_ROOT"]
        
    xunit_extension_dir = os.path.join(dafny_path, "Source", "XUnitExtensions", "Lit")
    if not os.path.exists(xunit_extension_dir):
        print("XUnitExtensions directory not found. Please check if dafny is cloned at the specified directory.")
        exit(1)
    
    # Get the number of mutated files
    mutated_file_count = get_mutated_file_count(args.registry_path)
    print(f"Found {mutated_file_count} mutated files.")
    
    replace_with = f"      this.passthroughEnvironmentVariables = passthroughEnvironmentVariables.Append(\"MUTATE_CSHARP_TRACER_FILEPATH\").Concat(Enumerable.Range(1, {mutated_file_count}).Select(i => $\"MUTATE_CSHARP_ACTIVATED_MUTANT{{i}}\")).ToArray();"
    print("The new line to be inserted is:")
    print(replace_with)
    
    # Apply patch to allow environment variables through Dafny XUnit extensions
    if not args.dry_run:
        shell_lit_command_path = os.path.join(xunit_extension_dir, "ShellLitCommand.cs")
        exit(replace_line(19, shell_lit_command_path, replace_with))