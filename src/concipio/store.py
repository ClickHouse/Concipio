"""The per-user store that holds review state outside the repository."""

import contextlib
import fcntl
import json
import os
import subprocess
from pathlib import Path


def data_home():
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


# Implements [CPO§V22]
def project_id(repo):
    out = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=repo,
                         capture_output=True, text=True, check=True).stdout
    return sorted(out.split())[0]


def remote_name(repo):
    out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo,
                         capture_output=True, text=True)
    if out.returncode != 0:
        out = subprocess.run(["git", "remote"], cwd=repo, capture_output=True, text=True)
        first = out.stdout.split()
        if not first:
            return Path(repo).name
        out = subprocess.run(["git", "remote", "get-url", first[0]], cwd=repo,
                             capture_output=True, text=True)
    return out.stdout.strip() or Path(repo).name


class Store:
    def __init__(self, repo):
        self.repo = Path(repo)
        self.dir = data_home() / "concipio" / project_id(repo)
        self.dir.mkdir(parents=True, exist_ok=True)
        name = self.dir / "name"
        if not name.exists():
            name.write_text(remote_name(repo) + "\n")

    @contextlib.contextmanager
    def lock(self):
        """Hold the project's lock, so that concurrent agents' commands do
        not overwrite each other's changes."""
        with (self.dir / "lock").open("w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read(self, rel, default):
        path = self.dir / rel
        return json.loads(path.read_text()) if path.exists() else default

    def write(self, rel, data):
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        tmp.replace(path)

    def append(self, rel, record):
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def lines(self, rel):
        path = self.dir / rel
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    @property
    def current(self):
        path = self.dir / "current"
        return path.read_text().strip() if path.exists() else None

    @current.setter
    def current(self, review_id):
        (self.dir / "current").write_text(review_id + "\n")
