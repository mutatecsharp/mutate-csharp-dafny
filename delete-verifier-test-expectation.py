#! /usr/bin/env python3.11

import re
import os
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


def delete_lines_in_file(file_path, patterns):
    # Read the file content
    with open(file_path, 'r') as file:
        lines = file.readlines()

    # If the pattern is not found, the original line is written back unmodified
    modified_lines = []
    
    for line in lines:
        if any(pattern.search(line) for pattern in patterns):
            print(f"-{line.strip()}")
            
            # Also remove the previous empty line
            if modified_lines and modified_lines[-1].strip() == '':
                modified_lines.pop()
            
            continue
            
        modified_lines.append(line)

    # Write the modified content back to the file
    with open(file_path, 'w') as file:
        file.writelines(modified_lines)


def process_directory(directory):
    supported_extensions = {'.dfy', '.expect', '.check'}
    
    # Define the pattern with capturing groups for the parts to be preserved
    did_not_attempt = re.compile(r'Dafny program verifier did not attempt verification')
    basic_pattern = re.compile(r'(Dafny program verifier finished with )\d+( verified, )\d+( errors?)')
    basic_assertion_pattern = re.compile(r'(Dafny program verifier finished with )\d+( assertions verified, )\d+( errors?)')
    check_pattern = re.compile(r'(// CHECK: .*Dafny program verifier finished with )\d+( verified, )\d+( errors?.*)')
    check_assertion_pattern = re.compile(r'(// CHECK: .*Dafny program verifier finished with )\d+( assertions verified, )\d+( errors?.*)')
    patterns = [did_not_attempt, basic_pattern, check_pattern, basic_assertion_pattern, check_assertion_pattern]
    
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            expect_filepath = os.path.join(dirpath, filename)
            
            if any(expect_filepath.endswith(extension) for extension in supported_extensions):
                # Replace the lines in the file
                print(f"Processing {expect_filepath}.")
                delete_lines_in_file(expect_filepath, patterns)
                

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", action="store_true", help="Experiment.")
    args = parser.parse_args()
    
    if not validate_volume_directory_exists():
        print('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)
    
    env = obtain_env_vars()
    
    # Locate dafny path based on the experiment flag
    if args.e:
        print("Running on clean-slate dafny codebase.")
        dafny_path = os.path.join(env["TESTBENCH"], "dafny")
    else:
        print("Running on mutated dafny codebase.")
        dafny_path = os.path.join(env["WORKSPACE"], "dafny")
        
    integration_test_path = os.path.join(dafny_path, "Source", "IntegrationTests", "TestFiles", "LitTests", "LitTest")
    
    if not os.path.exists(integration_test_path):
        print("Dafny integration test directory not found. Please clone the git repository in the corresponding directory.")
        exit(1)
    
    process_directory(integration_test_path)
    