#!/usr/bin/env python3
"""Build dist/fantasy-draft-copilot.zip: everything a second person needs (no cookies, no cache)."""
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {"cache", "__pycache__", "dist", "screenshots", ".git", ".pytest_cache"}
EXCLUDE_FILES = {"config.json", "drafted.txt", "targets.txt", "avoid.txt", "board.csv", "queue.txt", ".DS_Store"}


def main() -> None:
    dist = os.path.join(HERE, "dist")
    os.makedirs(dist, exist_ok=True)
    out = os.path.join(dist, "fantasy-draft-copilot.zip")
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(HERE):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for name in sorted(files):
                if name in EXCLUDE_FILES or name.endswith((".pyc", ".log", ".zip")):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, HERE)
                z.write(full, os.path.join("fantasy-draft", rel))
                count += 1
    print(f"Wrote {out} ({count} files, {os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
