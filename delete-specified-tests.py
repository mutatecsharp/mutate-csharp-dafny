#! /usr/bin/env python3.11

import os
import shlex
import subprocess
import argparse


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


def delete_file(path: str):
    if os.path.exists(path):
        try:
            os.remove(path)
            print("Deleted test: ", path)
        except Exception as e:
            print(f"Error deleting {path}: {e}")


# Delete both the specified testcase to delete and its expected output file (.dfy, .dfy.expect)
def delete_test_files(integration_test_dir: str, tests_to_delete: list, dry_run: bool):
    for test in tests_to_delete:
        test_path = os.path.join(integration_test_dir, test)
        expected_output_path = os.path.join(integration_test_dir, test + ".expect")
        
        if dry_run:
            print(f"[Dry run] Test file to delete: {test_path}")
            print(f"[Dry run] Expected output file to delete: {expected_output_path}")
        else:
            delete_file(test_path)
            delete_file(expected_output_path)
        

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("tests-to-delete", type=str, help="List of tests to delete, in text file.")
    parser.add_argument("-e", action='store_true', help="Experiment.")
    parser.add_argument("--dry-run", action='store_true', help="Dry run - displays which files are to be deleted.")
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
    
    if not os.path.exists(args.tests_to_delete):
        print(f"File {args.tests_to_delete} not found.")
        exit(1)
        
    with open(args.tests_to_delete) as f:
        tests_to_delete = f.read().splitlines()
    
    if args.dry_run:
        print("Performing dry run.")
        
    print(f"Assessed {len(tests_to_delete)} test(s) to be removed.")
    delete_test_files(integration_test_path, tests_to_delete, args.dry_run)