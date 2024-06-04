import os
import shutil

from itertools import groupby
from pathlib import Path
from loguru import logger


def all_equal(iterable):
    groups = groupby(iterable)
    return next(groups, True) and not next(groups, False)


def empty_directory(directory: Path):
    # Delete the entire contents of the directory
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            logger.error(f"Failed to delete {file_path}. Reason: {e}")
