import re
import os
import tempfile
import subprocess


def validate_volume_directory_exists():
    volume_dir = os.environ.get('VOLUME_ROOT')
    return volume_dir and os.path.exists(volume_dir)


def obtain_env_vars():
    # Sanity check: we should be in mutate-csharp-dafny directory
    if not os.path.exists('env.sh') or not os.path.exists('parallel.runsettings'):
        print('Please run this script from the root of the mutate-csharp-dafny directory.')
        exit(1)
        
    # Create a temporary shell script to source env.sh and print environment variables
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), mode='w') as temp_script:
        temp_script.write(
            f"""
            #!/bin/bash
            source {os.path.join(os.getcwd(), 'env.sh')}
            env
            """
        )
        temp_script.flush()
        os.chmod(temp_script.name, 0o755) # make the script executable
        
        # Execute the temporary script and capture the output
        process = subprocess.Popen([f"./{temp_script.name}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"Error sourcing env.sh: {stderr.decode()}")
        else:
            # Parse the output to get environment variables
            env_vars = stdout.decode().split("\n")
            env_dict = {}
            for var in env_vars:
                if "=" in var:
                    key, value = var.split("=", 1)
                    env_dict[key] = value
        
    return env_dict


def find_run_commands(test_filepath: str):
    pass


def process_directory(directory):
    run_commands = {}
    
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith('.dfy'):
                test_filepath = os.path.join(dirpath, filename)
                print(test_filepath)
                # commands = find_run_commands(test_filepath)
                # if commands:
                #     run_commands[filepath] = commands
    
    # return run_commands
    

if __name__ == '__main__':
    if not validate_volume_directory_exists():
        print('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)
        
    env = obtain_env_vars()
    
    # process_directory()