import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

CONFIG_FILENAME = "rocksdict-config.json"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def get_rocks_dir(rocksdb_dir: str, linksdir: str) -> str:
    """returns a rocks dir where CONFIG_FILENAME is writable"""
    try:
        testfile = Path(rocksdb_dir) / CONFIG_FILENAME
        with testfile.open("a"):
            pass
        return rocksdb_dir
    except (PermissionError, FileNotFoundError, OSError):
        logger.info(f"{rocksdb_dir}/{CONFIG_FILENAME} write error, creating shadow {linksdir}")
        return str(setup_shadow(Path(rocksdb_dir), Path(linksdir)))


def setup_shadow(rocksdb_dir: Path, linksdir: Path) -> Path:
    """Create a writable shadow of a read-only RocksDB directory.

    Symlinks all DB files/folders from *rocksdb_dir* into *linksdir*,
    except ``rocksdict-config.json`` which is copied (not linked).

    This works around the rocksdict read-only bug that prevents opening
    a database from a truly read-only mount.

    Args:
        rocksdb_dir: Path to the source (read-only) RocksDB directory.
        linksdir: Path to the destination shadow directory.

    Returns:
        The resolved path to the shadow directory.

    Raises:
        FileNotFoundError: If *rocksdb_dir* does not exist or is not a directory.
    """
    rocksdb_dir = Path(rocksdb_dir).resolve()
    linksdir = Path(linksdir).resolve()

    if not rocksdb_dir.is_dir():
        raise FileNotFoundError(f"Source directory '{rocksdb_dir}' does not exist or is not a directory.")

    # Create linksdir if it does not exist
    linksdir.mkdir(parents=True, exist_ok=True)

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
            shutil.copy2(item, target_path)
        else:
            target_path.symlink_to(item.resolve())

    return linksdir


def main() -> None:
    """CLI entry point: parse arguments and create a writable shadow of a read-only RocksDB directory."""
    parser = argparse.ArgumentParser(
        description="Workaround for rocksdict read-only bug by symlinking DB files and copying config."
    )
    parser.add_argument(
        "rocksdb_dir",
        type=Path,
        help="Path to the source (read-only) RocksDB directory",
    )
    parser.add_argument(
        "linksdir",
        type=Path,
        help="Path to the destination links directory",
    )

    args = parser.parse_args()

    try:
        setup_shadow(args.rocksdb_dir, args.linksdir)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
