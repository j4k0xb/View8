
import subprocess
import os
from Parser.sfi_file_parser import parse_file, parse_file_v15


def get_version(view8_dir, file_name):
    # Cross-platform pure-Python detector; understands both the legacy
    # (<= V8 13.x) and modern (V8 14+) version-hash algorithms.
    from Parser.version_detector import detect_file_version
    return detect_file_version(file_name)


def run_disassembler_binary(binary_path, file_name, out_file_name):
    # Ensure the binary exists
    if not os.path.isfile(binary_path):
        raise FileNotFoundError(
            f"The binary '{binary_path}' does not exist. "
            "You can specify a path to a similar disassembler version using the --path (-p) argument."
        )

    # Newer disassemblers support runtime-blob injection via env vars; pick up
    # companion files placed next to the binary automatically.
    env = os.environ.copy()
    binary_dir = os.path.dirname(os.path.abspath(binary_path))
    for env_var, file_name_blob in (
        ('V8DASM_SNAPSHOT_BLOB', 'hybrid_snapshot.bin'),
        ('V8DASM_RO_IMAGE', 'ro_image.bin'),
    ):
        companion = os.path.join(binary_dir, file_name_blob)
        if os.path.isfile(companion) and env_var not in env:
            env[env_var] = companion

    # Open the output file in write mode
    with open(out_file_name, 'w') as outfile:
        # Call the binary with the file name as argument and pipe the output to the file
        try:
            result = subprocess.run([binary_path, file_name], stdout=outfile, stderr=subprocess.PIPE, text=True, env=env)

            # Exit code 77 signals a late crash after partial (still usable) output.
            if result.returncode == 77:
                print("Warning: disassembler crashed after partial output; "
                      "the tail of the file may be truncated.")

            # Check the return status code
            if result.stderr and result.returncode not in (0, 77):
                raise RuntimeError(
                    f"Binary execution failed with status code {result.returncode}: {result.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Error calling the binary: {e}")


def parse_v8cache_file(file_name, out_name, view8_dir, binary_path):
    if not binary_path:
        print(f"Detecting version.")
        version = get_version(view8_dir, file_name)
        print(f"Detected version: {version}.")
        # Search the versioned directory layout first (Bin/<version>/v8dasm),
        # then the legacy flat layout (Bin/<version>.exe).
        for candidate in (
            os.path.join(view8_dir, 'Bin', version, 'v8dasm'),
            os.path.join(view8_dir, 'Bin', f'{version}.exe'),
        ):
            if os.path.isfile(candidate):
                binary_path = candidate
                break
    print(f"Executing disassembler binary: {binary_path}.")
    run_disassembler_binary(binary_path, file_name, out_name)
    print(f"Disassembly completed successfully.")


def parse_disassembled_file(out_name):
    print(f"Parsing disassembled file.")
    # Block-based parser: handles both legacy (<=10.8) and newer (15.x)
    # disassembly layouts, including SharedFunctionInfo blocks nested
    # inside operand output.
    all_func = parse_file_v15(out_name)
    print(f"Parsing completed successfully.")
    return all_func
