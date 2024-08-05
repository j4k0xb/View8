import os
import struct
import subprocess

import requests
from parse import parse

from Parser.sfi_file_parser import parse_file


def hash_value_unsigned(v):
    v = ((v << 15) - v - 1) & 0xFFFFFFFF
    v = (v ^ (v >> 12)) & 0xFFFFFFFF
    v = (v + (v << 2)) & 0xFFFFFFFF
    v = (v ^ (v >> 4)) & 0xFFFFFFFF
    v = (v * 2057) & 0xFFFFFFFF
    v = (v ^ (v >> 16)) & 0xFFFFFFFF
    return v


def hash_combine_64(seed, value):
    m = 0xC6A4A7935BD1E995
    r = 47

    value = (value * m) & 0xFFFFFFFFFFFFFFFF
    value = (value ^ (value >> r)) & 0xFFFFFFFFFFFFFFFF
    value = (value * m) & 0xFFFFFFFFFFFFFFFF

    seed = (seed ^ value) & 0xFFFFFFFFFFFFFFFF
    seed = (seed * m) & 0xFFFFFFFFFFFFFFFF
    return seed


def version_hash_64(major, minor, build, patch):
    seed = 0
    seed = hash_combine_64(seed, hash_value_unsigned(patch))
    seed = hash_combine_64(seed, hash_value_unsigned(build))
    seed = hash_combine_64(seed, hash_value_unsigned(minor))
    seed = hash_combine_64(seed, hash_value_unsigned(major))
    return seed & 0xFFFFFFFF


def get_version(file_name):
    with open(file_name, "rb") as f:
        f.seek(4)
        version_hash = struct.unpack("<I", f.read(4))[0]

    node_versions = requests.get("https://nodejs.org/dist/index.json").json()
    electron_versions = requests.get(
        "https://releases.electronjs.org/releases.json"
    ).json()

    for version in node_versions + electron_versions:
        v8_version = version["v8"].replace("-electron.0", "")
        major, minor, build, patch = parse("{:d}.{:d}.{:d}.{:d}", v8_version) or parse(
            "{:d}.{:d}.{:d}.{:d}", v8_version + ".0"
        )
        if version_hash == version_hash_64(major, minor, build, patch):
            return v8_version

    raise RuntimeError(f"Failed to detect version for file {file_name}.")


def run_disassembler_binary(binary_path, file_name, out_file_name):
    # Ensure the binary exists
    if not os.path.isfile(binary_path):
        raise FileNotFoundError(
            f"The binary '{binary_path}' does not exist. "
            "You can specify a path to a similar disassembler version using the --path (-p) argument."
        )

    # Open the output file in write mode
    with open(out_file_name, 'w') as outfile:
        # Call the binary with the file name as argument and pipe the output to the file
        try:
            result = subprocess.run([binary_path, file_name], stdout=outfile, stderr=subprocess.PIPE, text=True)

            # Check the return status code
            if result.stderr:
                raise RuntimeError(
                    f"Binary execution failed with status code {result.returncode}: {result.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Error calling the binary: {e}")


def parse_v8cache_file(file_name, out_name, view8_dir, binary_path):
    if not binary_path:
        print(f"Detecting version.")
        version = get_version(file_name)
        print(f"Detected version: {version}.")
        # Define the binary name using the version
        binary_name = f"{version}.exe"
        binary_path = os.path.join(view8_dir, 'Bin', binary_name)
    print(f"Executing disassembler binary: {binary_path}.")
    run_disassembler_binary(binary_path, file_name, out_name)
    print(f"Disassembly completed successfully.")


def parse_disassembled_file(out_name):
    print(f"Parsing disassembled file.")
    all_func = parse_file(out_name)
    print(f"Parsing completed successfully.")
    return all_func
