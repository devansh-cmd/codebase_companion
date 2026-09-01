"""
Repo walker.

Point it at a cloned repo, get back a list of the files worth indexing.

THE APPROACH
------------
- Walk the directory tree once. Decide keep-or-drop for each entry.
- That is O(n). "O(n)" = order n = the work grows in direct proportion to the
  number of entries on disk. Double the files, double the work.
- You cannot beat O(n) here. You have to look at a thing at least once to
  reject it.
- So the speed does NOT come from the complexity class. It comes from never
  looking at most of the tree at all.
- A repo's .git folder usually holds more files than its source code does.
  A venv/ folder can hold tens of thousands.
- os.walk hands us a directory's subdirectory list BEFORE it descends into it.
- Delete names from that list and those folders are never opened. That is the
  whole design. Everything else below is just filtering the leftovers.

WHY NOT rglob
-------------
- Path.rglob("*") looks cheap because it returns a generator.
- A "generator" produces items one at a time as you ask for them, instead of
  building the whole list up front.
- But lazy is not the same as selective. rglob has no way to skip a folder.
- It descends into .git and venv anyway, and you filter afterwards.
- By then you have already paid to visit every entry.
- Measured on this repo: rglob touched 54,062 entries in 0.496s.
  This walker returned the real files in 0.001s.

WHAT IT WILL AND WILL NOT SKIP BY NAME
--------------------------------------
- A name is only skipped if a TOOL created the folder and fixed that name:
  .git, __pycache__, node_modules, site-packages.
- Then the name really does guarantee the contents.
- Names a person chose are NOT skipped, however conventional. "build", "dist",
  "out", "target" and "env" were removed for this reason.
- A folder that a machine made but a person named -- a virtualenv -- is caught
  by looking inside it for a marker file instead. See DIR_MARKERS.
- Want a folder of your own pruned? Pass extra_skip_dirs={"artifacts"} so the
  guess is yours and it is visible at the call site.

WHY IT REPORTS WHAT IT SKIPPED
------------------------------
- Any skip can still be wrong, and a wrong one loses real source silently.
- There is no error. The count just comes back a bit lower, and no number
  looks obviously wrong.
- You would not notice at the time. You would notice weeks later, as vague
  answers from the RAG system, and go debug the chunking instead.
- So `return_skipped=True` reports what was dropped and why. It changes no
  decision. It only stops the decisions being invisible.

Run:
    python rag/walk_repo.py <path-to-repo>
    python rag/walk_repo.py . --deep-count
"""

import os
import sys
from collections import Counter
from pathlib import Path

# Directory names we never descend into.
# Matched by exact name, not by full path. So "node_modules" is skipped
# wherever it appears in the tree, at any depth.
#
# THE RULE FOR THIS LIST: a name only belongs here if a TOOL created the folder
# and fixed that name. Then the name genuinely guarantees the contents, and
# skipping it cannot lose your work.
#
# Names a PERSON chose are not allowed here, however conventional. "build",
# "dist", "target", "out" and "env" used to be on this list and have been
# removed -- a repo can legitimately keep real work in a folder called "out",
# and skipping it would delete that work from the index with no error.
#
# If you want one of those pruned for your repo, pass it explicitly:
#     walk_repo(root, extra_skip_dirs={"artifacts"})
# That way the guess is yours and it is visible at the call site.
SKIP_DIRS = {
    # version control internals -- created and named by the VCS
    ".git", ".hg", ".svn",
    # tool caches -- name fixed by the tool that writes them
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".ipynb_checkpoints", ".gradle", ".cargo", ".terraform",
    # package installs -- written by a package manager, never hand-edited
    "site-packages", "node_modules", "bower_components",
    # framework build output -- name fixed by the framework
    ".next", ".nuxt",
}

# Some machine-made folders cannot be recognised by name, because the person
# chose the name. A virtual environment is the big one:
#     python -m venv venv      -> "venv"
#     python -m venv myproject -> "myproject"
# Same contents, any name. Name matching cannot win here.
#
# But every virtualenv contains a file called pyvenv.cfg, written by the venv
# module itself. Checking for that marker identifies the folder by what it IS
# rather than what it is called. It catches a venv whatever you named it, and
# it will not touch a folder that merely happens to be called "venv".
#
# Cost is one existence check per directory. A repo has far fewer directories
# than files, so this is negligible.
DIR_MARKERS = {
    "pyvenv.cfg": "virtualenv",
}

# File extensions that are not text we can read.
# Looking something up in a set takes about the same time no matter how big the
# set is, so this stays cheap however long the list grows.
SKIP_EXTS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".o", ".a", ".obj",
    ".exe", ".bin", ".class", ".jar", ".wasm",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ogg",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".db", ".sqlite", ".sqlite3", ".pkl", ".npy", ".npz", ".bin",
    ".lock", ".pack", ".idx",
}

# 2 MB. Past this size, a text file is almost always generated, minified or a
# data dump rather than something a person wrote.
MAX_BYTES = 2_000_000


def walk_repo(
    root,
    skip_dirs=SKIP_DIRS,
    extra_skip_dirs=None,
    skip_exts=SKIP_EXTS,
    markers=DIR_MARKERS,
    max_bytes=MAX_BYTES,
    skip_hidden=True,
    return_skipped=False,
):
    """Return a list of Paths to the files in `root` that are worth reading.

    root           : the repo folder to walk
    skip_dirs      : directory names to never descend into
    extra_skip_dirs: extra names to skip, ADDED to skip_dirs rather than
                     replacing them (see note below)
    skip_exts      : file extensions to drop (lowercase, with the dot)
    markers        : {filename: label} -- a directory containing that file is
                     machine-made and gets pruned whatever it is named
    max_bytes      : drop files larger than this; None disables the check
    skip_hidden    : also drop dotfiles and dot-directories not already listed
    return_skipped : if True, return (files, skipped) instead of just files

    Why extra_skip_dirs exists when you could pass skip_dirs yourself:
        walk_repo(root, skip_dirs=SKIP_DIRS | {"artifacts"})   # adds
        walk_repo(root, skip_dirs={"artifacts"})               # REPLACES
    Those two lines look almost identical. The second one throws the defaults
    away, so venv/ is walked and you get tens of thousands of library files.
    extra_skip_dirs cannot be got wrong that way.
    """
    # .resolve() turns a relative path like "." into a full absolute path.
    # Without it the returned Paths stay relative to wherever you ran the
    # script from, and would point at the wrong place if anything later
    # changed the working directory.
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    # `|` on two sets means union: everything in either one.
    if extra_skip_dirs:
        skip_dirs = set(skip_dirs) | set(extra_skip_dirs)

    files = []

    # What we threw away, and why. Counter is a dict built for tallying:
    # reading a key that was never set gives 0 instead of raising KeyError,
    # so `counter[x] += 1` works on the first sight of x.
    skipped = {
        "dirs": {},              # folder name -> list of paths pruned
        "reasons": {},           # folder name -> why it was pruned
        "exts": Counter(),       # extension -> how many files dropped
        "hidden": 0,             # dotfiles dropped
        "too_big": 0,            # files over max_bytes
        "stat_error": 0,         # files we could not inspect
    }

    # os.walk yields one tuple per directory: (path, subdirectories, files).
    #
    # topdown=True means we are handed a directory's subdirectory list BEFORE
    # os.walk descends into them. It is the default, and it is the entire
    # reason this is fast: editing that list steers where the walk goes next.
    #
    # followlinks=False: a "symlink" (symbolic link) is a file whose only
    # content is a pointer to another path. A symlink can point back up to a
    # parent folder. Follow it and you walk that subtree again, meet the same
    # link again, and loop forever -- the walk never returns. False stops that.
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):

        here = Path(dirpath)

        # Decide keep-or-prune for each subdirectory, recording WHY.
        #
        # The decision is made once and used for both the pruning and the
        # report. An earlier version tested the same condition twice, in two
        # places. That works until someone edits one and not the other, at
        # which point the report quietly stops describing what actually
        # happened. One decision, one place.
        #
        # Note we do NOT count the files inside a pruned folder -- that would
        # mean walking it, which is precisely the work pruning exists to
        # avoid. Use --deep-count when you actually want those numbers.
        keep_dirs = []
        for d in dirnames:
            reason = None
            if d in skip_dirs:
                reason = "tool-generated"
            elif skip_hidden and d.startswith("."):
                reason = "hidden"
            else:
                # Content check: is this a machine-made folder wearing a
                # human-chosen name? .exists() can raise on a broken symlink
                # or a folder we lack permission for, so guard it -- an
                # unreadable directory should be walked normally, not crash
                # the whole run.
                for marker, label in markers.items():
                    try:
                        if (here / d / marker).exists():
                            reason = label
                            break
                    except OSError:
                        continue

            if reason is None:
                keep_dirs.append(d)
            else:
                rel = str((here / d).relative_to(root))
                skipped["dirs"].setdefault(d, []).append(rel)
                skipped["reasons"][d] = reason

        # --- prune: this is the line that saves all the time ----------------
        #
        # It MUST be a slice assignment. That is the `[:]` on the left.
        # Slice assignment replaces the contents of the existing list, keeping
        # the same list object in memory.
        #
        # Writing `dirnames = [...]` instead would be "rebinding": pointing the
        # name at a brand-new list. os.walk still holds the original one, and
        # re-reads that same original object after this loop body to decide
        # where to descend.
        #
        # So rebinding means you walk into .git while believing you excluded
        # it. No error, no warning. Just a walk hundreds of times slower.
        dirnames[:] = keep_dirs

        for name in filenames:
            if skip_hidden and name.startswith("."):
                skipped["hidden"] += 1
                continue

            # .suffix is the last extension on a Path, including the dot.
            # It only takes the last one: "archive.tar.gz" gives ".gz".
            # Fine here, because .gz is in the skip list anyway.
            #
            # But it is also why TensorBoard logs slip through. A file named
            # events.out.tfevents.1770594807.devs.13236.0 has suffix ".0",
            # which is not in SKIP_EXTS. Extension filtering cannot catch
            # those; skipping their folder can.
            ext = Path(name).suffix.lower()
            if ext in skip_exts:
                skipped["exts"][ext] += 1
                continue

            path = here / name

            if max_bytes is not None:
                # "stat" asks the operating system for a file's metadata: size,
                # dates, permissions. It does not open or read the file, so it
                # is cheap.
                #
                # It can still fail. A broken symlink points at something that
                # was deleted. A file may deny us permission. Either raises
                # OSError, the error type for a failed OS-level file operation.
                #
                # Without this try/except, one bad file 40,000 entries into a
                # large repo kills the whole walk, and you lose every result
                # collected so far. With it, that one file is skipped.
                try:
                    if path.stat().st_size > max_bytes:
                        skipped["too_big"] += 1
                        continue
                except OSError:
                    skipped["stat_error"] += 1
                    continue

            files.append(path)

    # Returning a different shape depending on a flag is a little impure, but
    # it keeps the common call -- walk_repo(root) -> list -- short and honest.
    if return_skipped:
        return files, skipped
    return files


def count_files_under(path):
    """Count every file beneath `path`, no filtering.

    Only for the --deep-count report. This deliberately does the expensive
    thing the walker avoids: it opens the pruned folders to see how big they
    actually were. Worth it once, as an audit. Not worth it every run.
    """
    total = 0
    for _, _, filenames in os.walk(path, followlinks=False):
        total += len(filenames)
    return total


if __name__ == "__main__":
    # sys.argv is the list of words you typed to run this.
    # [0] is the script's own name, so [1:] are the real arguments.
    args = sys.argv[1:]
    deep = "--deep-count" in args
    args = [a for a in args if not a.startswith("--")]
    target = args[0] if args else "."

    import time
    # perf_counter is a high-resolution timer meant for measuring durations.
    # Its absolute value means nothing on its own; only the difference between
    # two readings tells you anything.
    start = time.perf_counter()
    found, skipped = walk_repo(target, return_skipped=True)
    elapsed = time.perf_counter() - start

    root = Path(target).resolve()
    print(f"{len(found)} files kept in {elapsed:.3f}s under {root}")

    # --- what we kept -------------------------------------------------------
    # Count how many files carry each extension.
    # This is the fastest way to spot a folder you forgot to skip: look for an
    # extension you did not expect with a suspiciously big count.
    counts = Counter(p.suffix or "(no ext)" for p in found)

    print("\ntop extensions kept:")
    for ext, n in counts.most_common(10):
        print(f"  {ext:12} {n}")

    # --- what we threw away -------------------------------------------------
    print("\nskipped directories:")
    if not skipped["dirs"]:
        print("  (none)")
    for name, paths in sorted(skipped["dirs"].items(), key=lambda kv: -len(kv[1])):
        if deep:
            files_inside = sum(count_files_under(root / p) for p in paths)
            print(f"  {name:} {len(paths):3} dir(s)  {files_inside:6} files inside"
                  f"  [{skipped['reasons'].get(name, '?')}]")
        else:
            print(f"  {name:} {len(paths):3} dir(s)"
                  f"  [{skipped['reasons'].get(name, '?')}]")
        # Show where, so an unexpected name is traceable. Only the first few.
        for p in paths[:3]:
            print(f"      {p}")
        if len(paths) > 3:
            print(f"      ... and {len(paths) - 3} more")

    if not deep:
        print("\n  (pass --deep-count to also count the files inside them --")
        print("   that opens the skipped folders, which is the slow thing)")

    dropped_ext = sum(skipped["exts"].values())
    print(f"\nskipped files: {dropped_ext} by extension, "
          f"{skipped['hidden']} hidden, {skipped['too_big']} too big, "
          f"{skipped['stat_error']} unreadable")
    for ext, n in skipped["exts"].most_common(5):
        print(f"  {ext:12} {n}")

    # --- where the kept files actually live ---------------------------------
    # Deliberately NOT "first 20 files". os.walk returns root files first, then
    # subfolders in alphabetical order, so a first-N preview shows you whatever
    # sorts earliest and silently omits the rest. That reads as "my folder was
    # skipped" when it was only off the bottom of the list.
    # Totals per top-level folder cannot mislead that way.
    #
    # relative_to(root) strips the long absolute prefix off so output is
    # readable. It works only because both paths were resolved above.
    # .parts splits a path into its pieces: ("product", "models", "cnn.py").
    # parts[0] is therefore the top-level folder, or the filename itself for a
    # file sitting directly in root.
    tops = Counter(
        p.relative_to(root).parts[0] if len(p.relative_to(root).parts) > 1
        else "(root)"
        for p in found
    )
    print("\nkept files by top-level folder:")
    for name, n in tops.most_common():
        print(f"  {name:28} {n}")

    print("\nsample of kept files:")
    # Take a spread across the whole list rather than the first few, so a big
    # folder late in the walk still shows up here.
    step = max(1, len(found) // 10)
    for p in found[::step][:10]:
        print(f"  {p.relative_to(root)}")
