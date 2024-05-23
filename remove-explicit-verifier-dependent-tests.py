#! /usr/bin/env python3.11

import re
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
    

def find_run_commands(run_pattern: re.Pattern, test_filepath: str):
    with open(test_filepath, 'r') as file:
        content = file.read()
        
    return run_pattern.findall(content) # list[str]


def command_depends_on_verifier(verification_patterns, run_commands):
    return len(run_commands) > 0 and any(pattern in single_command for pattern in verification_patterns for single_command in run_commands)


def process_directory(directory):
    run_pattern = re.compile(r'^\s*//\s*RUN:\s*(.*)$', re.MULTILINE)
    verification_patterns = {
        r"--no-verify:false",
        r"--no-verify=false",
        r"--no-verify false",
        r"dafny verify",
        r"%baredafny verify",
        r"dafny generate-tests",
        r"%baredafny generate-tests",
        r"--verify-included-files",
        r"-verifyAllModules",
        r"/verifySeparately",
        r"/dafnyVerify:1",
        r"-dafnyVerify:1",
        r"/prover",
        r"/restartProver",
        r"%verify",
        r"%boogie",
        r"%testDafnyForEachResolver",
        r"dafny measure-complexity",
        r"--solver-log",
        r"-verificationLogger:",
    }
    files_to_remove = []
    
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith('.dfy'):
                test_filepath = os.path.join(dirpath, filename)
                
                if command_depends_on_verifier(verification_patterns, find_run_commands(run_pattern, test_filepath)):
                    files_to_remove.append(test_filepath)
                    files_to_remove.append(f"{test_filepath}.expect")
    
    return files_to_remove
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", action='store_true', help="Experiment.")
    parser.add_argument("--dry-run", action='store_true', help="Dry run - displays which files are to be deleted.")
    args = parser.parse_args()
    
    if not validate_volume_directory_exists():
        print('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)
        
    env = obtain_env_vars()
    
    # Locate dafny path based on the experiment flag
    if args.e:
        print("Running on non-mutated dafny codebase.")
        dafny_path = os.path.join(env["TESTBENCH"], "dafny")
    else:
        dafny_path = os.path.join(env["WORKSPACE"], "dafny")
        
    integration_test_path = os.path.join(dafny_path, "Source", "IntegrationTests", "TestFiles", "LitTests", "LitTest")
    generated_docs_test_path = os.path.join(dafny_path, "Test", "docexamples")
    
    if not os.path.exists(integration_test_path):
        print("Dafny integration test directory not found. Please clone the git repository in the corresponding directory.")
        exit(1)
    
    if not os.path.exists(generated_docs_test_path):
        print("Dafny generated test directory not found. Please generate test files in docs using ./check-examples -c HowToFAQ/Errors-*.md.")
        exit(1)
    
    integration_testfiles_to_remove = process_directory(integration_test_path)
    generated_testfiles_to_remove = process_directory(generated_docs_test_path)
    files_to_remove = generated_testfiles_to_remove + integration_testfiles_to_remove
    
    if args.dry_run:
        print("Performing dry run.")

    if args.dry_run:
        print(f"Assessed {len(files_to_remove)} files to be removed.")
    else:
        for file in files_to_remove:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    print(f"Error deleting {file}: {e}")