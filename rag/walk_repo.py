"""Find the files in a repo worth reading. Returns a list of Paths."""

import os
from pathlib import Path

# Only names a tool creates AND fixes, so the name really does tell you what is
# inside. Names a person picked -- build, dist, out, target, env -- are not here:
# a repo can legitimately keep real work in a folder called "out".
SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".ipynb_checkpoints", ".gradle", ".cargo", ".terraform",
    "site-packages", "node_modules", "bower_components",
    ".next", ".nuxt",
}

# A virtualenv is machine-made but you name it yourself (`python -m venv anything`),
# so its name proves nothing. Every one contains pyvenv.cfg, written by Python.
# Recognise the folder by what it holds, not what it is called.
VENV_MARKER = "pyvenv.cfg"

# Binary files. Nothing to read, so nothing to index.
SKIP_EXTS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".o", ".a", ".obj",
    ".exe", ".bin", ".class", ".jar", ".wasm",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ogg",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".db", ".sqlite", ".sqlite3", ".pkl", ".npy", ".npz",
    ".lock", ".pack", ".idx",
}

# A text file past 2 MB is a data dump or minified output, not writing. Left in,
# it becomes one enormous useless chunk in the index.
MAX_BYTES = 2_000_000


def walk_repo(root):
    """Return every readable file under root, skipping tool-made directories."""
    # Absolute path, so the results stay valid if anything later changes the
    # working directory.
    root = Path(root).resolve()

    # Fail loudly on a typo'd path. os.walk on a missing folder yields nothing,
    # so without this you would get an empty list and assume the repo was empty.
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    files = []

    # followlinks=False: a symlink (a file that is just a pointer to another
    # path) can point back at a parent folder. Follow it and you walk the same
    # subtree forever and never return.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)

        # This is the line that makes it fast, and the only subtle one.
        # os.walk hands us the subdirectory list before it descends, then reads
        # that same list again to decide where to go next. So editing it steers
        # the walk, like crossing streets off a map before the driver looks
        # again. That is why we never open .git at all, rather than opening it
        # and discarding what we find.
        # It must be `dirnames[:] = ...`. Plain `dirnames = ...` builds a new
        # list that os.walk never sees, and .git gets walked anyway -- no error,
        # just slow.
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and not d.startswith(".")
            and not (here / d / VENV_MARKER).exists()
        ]

        for name in filenames:
            if name.startswith(".") or Path(name).suffix.lower() in SKIP_EXTS:
                continue

            path = here / name
            try:
                # stat asks the OS for a file's size without opening it. It
                # raises on a broken symlink or a file we cannot read -- skip
                # that one file, because otherwise a single bad entry halfway
                # through a large repo throws away every result so far.
                if path.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue

            files.append(path)

    return files
