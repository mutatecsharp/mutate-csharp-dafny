#! /usr/bin/env python3.11

import os
import datetime
import shlex
import argparse
import subprocess
import xml.etree.ElementTree as ET


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


def parse_trx_result(trx_path: str):
    if not os.path.exists(trx_path):
        print(f"File {trx_path} not found.")
        return 1
    
    tree = ET.parse(trx_path)
    root = tree.getroot()
    
    # Define the namespace (defined in the .trx files)
    namespace = {'ns': 'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
    
    # Extract the test results
    results = []
    
    def convert_to_timedelta(duration):
        hours, minutes, seconds = duration.split(':')
        seconds, microseconds = seconds.split('.')
        microseconds = microseconds[:-1]
        return datetime.timedelta(hours=int(hours), minutes=int(minutes), seconds=int(seconds), microseconds=int(microseconds))

    
    for unit_test_result in root.findall('.//ns:UnitTestResult', namespace):
        test_name = unit_test_result.get('testName')
        outcome = unit_test_result.get('outcome')
        duration = unit_test_result.get('duration')
        error_message = None
        error_stack_trace = None

        if outcome == 'Failed':
            output = unit_test_result.find('.//ns:Output', namespace)
            if output is not None:
                error_info = output.find('.//ns:ErrorInfo', namespace)
                if error_info is not None:
                    error_message = error_info.find('.//ns:Message', namespace).text
                    error_stack_trace = error_info.find('.//ns:StackTrace', namespace).text

        results.append({
            'test_name': test_name,
            'outcome': outcome,
            'duration': convert_to_timedelta(duration),
            'error_message': error_message,
            'error_stack_trace': error_stack_trace
        })

    return results


def print_test_summary(results):
    total_tests = len(results)
    passed_tests = len([result for result in results if result['outcome'] == 'Passed'])
    failed_tests = len([result for result in results if result['outcome'] == 'Failed'])
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed Tests: {passed_tests}")
    print(f"Failed Tests: {failed_tests}")
    

def print_passing_tests(results: list, sort_by_duration: bool, verbose: bool):
    passed_results = [result for result in results if result['outcome'] == 'Passed']
    
    if sort_by_duration:
        passed_results.sort(key=lambda x: (x['duration']))
    
    if verbose:
        for result in passed_results:
            print(f"Test Name: {result['test_name']}")
            print(f"Duration: {result['duration']}")
            print('-' * 40)
        
        passed_duration = sum((result['duration'] for result in passed_results), datetime.timedelta())
        
        failed_results = [result for result in results if result['outcome'] == 'Failed']
        failed_duration = sum((result['duration'] for result in failed_results), datetime.timedelta())
        print(f"Passed tests total duration (Sequential): {passed_duration}")
        print(f"Failed tests total duration (Sequential): {failed_duration}")
    else:
        for result in passed_results:
            print(result['test_name'])
            
            
def print_failed_tests(results: list, verbose: bool):
    failed_results = [result for result in results if result['outcome'] == 'Failed']
    
    if verbose:
        for result in failed_results:
            print(f"Test Name: {result['test_name']}")
            print(f"Duration: {result['duration']}")
            print(f"Error Message: {result['error_message']}")
            print(f"Error Stack Trace: {result['error_stack_trace']}")
            print('-' * 40)
    else:
        for result in failed_results:
            print(result['test_name'])


def print_test_results(results):
    for result in results:
        print(f"Test Name: {result['test_name']}")
        print(f"Outcome: {result['outcome']}")
        print(f"Duration: {result['duration']}")
        if result['outcome'] == 'Failed':
            print(f"Error Message: {result['error_message']}")
            print(f"Error Stack Trace: {result['error_stack_trace']}")
        print('-' * 40)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("trx_file", type=str, help="Parses .trx file and extracts test run information.")
    parser.add_argument("--passing-tests", action="store_true", help="Print passing tests.")
    parser.add_argument("--failed-tests", action="store_true", help="Print failed tests.")
    parser.add_argument("--verbose", action="store_true", help="Print verbose output.")
    parser.add_argument("--ascending-duration", action="store_true", help="Sort the tests by duration.")
    args = parser.parse_args()
    
    if not validate_volume_directory_exists():
        print('Volume directory not found. Please set VOLUME_ROOT environment variable.')
        exit(1)
    
    env = obtain_env_vars()
    
    if parser.passing_tests and parser.failed_tests:
        print("Please specify either --passing-tests or --failed-tests.")
        exit(1)
    
    # Parse the .trx file
    test_results = parse_trx_result(args.trx_file)
    
    if args.passing_tests:
        print_passing_tests(test_results, args.ascending_duration, args.verbose)
    elif args.failed_tests:
        if args.ascending_duration:
            print(f"Note: --ascending-duration flag is ignored for failed tests.")
        print_failed_tests(test_results, args.verbose)
    else:
        print_test_results(test_results)
        print_test_summary(test_results)
    