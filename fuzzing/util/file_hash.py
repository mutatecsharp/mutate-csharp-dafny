import hashlib

from pathlib import Path


def compute_file_hash(file_path: Path) -> str:
    """
    Compute the hash of a file using SHA256 algorithm.

    :param file_path: Path to the file.
    :return: Hexadecimal hash string.
    """
    # Create a hash object
    hash_func = hashlib.sha256()

    # Open the file in binary mode
    with file_path.open('rb') as file:
        # Read the file in chunks
        chunk_size = 8192
        while chunk := file.read(chunk_size):
            hash_func.update(chunk)

    # Get the hexadecimal digest of the hash
    return hash_func.hexdigest()
