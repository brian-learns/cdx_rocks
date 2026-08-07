import argparse
import shutil
import sys
from pathlib import Path

CONFIG_FILENAME = "rocksdict-config.json"

def main():
    parser = argparse.ArgumentParser(
        description="Workaround for rocksdict read-only bug by symlinking DB files and copying config."
    )
    parser.add_argument(
        "rocksdb_dir",
        type=Path,
        help="Path to the source (read-only) RocksDB directory"
    )
    parser.add_argument(
        "linksdir",
        type=Path,
        help="Path to the destination links directory"
    )

    args = parser.parse_args()

    rocksdb_dir = args.rocksdb_dir.resolve()
    linksdir = args.linksdir.resolve()

    # Validate source directory
    if not rocksdb_dir.is_dir():
        print(f"Error: Source directory '{rocksdb_dir}' does not exist or is not a directory.", file=sys.stderr)
        sys.exit(1)

    # 1. Create linksdir if it does not exist
    linksdir.mkdir(parents=True, exist_ok=True)

    # Process each item in the rocksdb directory
    for item in rocksdb_dir.iterdir():
        target_path = linksdir / item.name

        # Skip if linksdir is located inside rocksdb_dir to avoid recursive loops
        if item.resolve() == linksdir:
            continue

        # Clean up existing file/link in target directory to prevent FileExistsError
        if target_path.exists() or target_path.is_symlink():
            if target_path.is_dir() and not target_path.is_symlink():
                shutil.rmtree(target_path)
            else:
                target_path.unlink()

        if item.name == CONFIG_FILENAME:
            # 3. Create a copy of rocksdict-config.json in the linksdir
            shutil.copy2(item, target_path)
        else:
            # 2. Create symbolic links for each file/folder except rocksdict-config.json
            target_path.symlink_to(item.resolve())

if __name__ == "__main__":
    main()
