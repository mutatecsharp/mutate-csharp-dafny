#! /usr/bin/env python3.11

import os
import time
import shutil
import shlex
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path

RETENTION_TIME = 600 # seconds

class DirectoryWatcher(FileSystemEventHandler):
    def __init__(self, directory: str, retention_time):
        self.directory = directory
        self.retention_time = retention_time

    def on_any_event(self, event):
        self.delete_old_directories()

    def delete_old_directories(self):
        current_time = time.time()
        for dirname in os.listdir(self.directory):
            dir_path = os.path.join(self.directory, dirname)
            if os.path.isdir(dir_path):
                dir_age = current_time - os.path.getmtime(dir_path)
                if dir_age > self.retention_time:
                    try:
                        shutil.rmtree(dir_path)
                        print(f"Deleted directory {dir_path}")
                    except Exception as e:
                        print(f"Error deleting directory {dir_path}: {e}")


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
    proc = subprocess.Popen(command, stdout=subprocess.PIPE)
    for line in proc.stdout:
        decoded_line = line.decode('utf-8').strip()
        (key, _, value) = decoded_line.partition("=")
        env_dict[key] = value
    proc.communicate()

    return env_dict


if __name__ == '__main__':
    if not validate_volume_directory_exists():
        print('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)

    env = obtain_env_vars()

    if 'MUTATED_ARTIFACT_PATH' not in env:
        print('artifact path not set for mutated Dafny.')
        exit(1)

    compilation_artifact_path = Path(env['MUTATED_ARTIFACT_PATH']) / "compilations"
    if not compilation_artifact_path.exists():
        compilation_artifact_path.mkdir(parents=True)

    event_handler = DirectoryWatcher(str(compilation_artifact_path), RETENTION_TIME)
    observer = Observer()
    observer.schedule(event_handler, str(compilation_artifact_path), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
