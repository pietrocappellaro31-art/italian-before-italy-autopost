"""
Public-repo safety scan. Run before every push (CI runs it too).

Fails if the repository contains anything that must stay private:
  * raw or working audio (.m4a .wav .mp3 .aac .caf .flac .aiff .ogg); finished Reels are MP4 in media/ only
  * secrets: env files, Meta access tokens (EAA...), GitHub tokens, private keys
  * files outside the allowed layout, or media over the size ceiling
Exit 0 = clean.
"""

import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
AUDIO = {".m4a", ".wav", ".mp3", ".aac", ".caf", ".flac", ".aiff", ".aif", ".ogg", ".opus"}
BANNED_NAMES = {".env", "credentials.json", "token.txt"}
SECRET_PATTERNS = [
    re.compile(rb"EAA[A-Za-z0-9]{40,}"),                    # Meta access tokens
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),             # GitHub tokens
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
ALLOWED_TOP = {"README.md", ".gitignore", "publish.py", "posts.json", "requirements.txt", ".github", ".devcontainer",
               "build", "tests", "media", "docs", "skills"}
MEDIA_EXT = {".jpg", ".jpeg", ".mp4"}
MAX_MEDIA_BYTES = 100 * 1024 * 1024


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
        files = [REPO / f for f in out.decode().split("\0") if f]
        if files:
            return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return [p for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts]


def scan(files):
    problems = []
    for path in files:
        rel = path.relative_to(REPO)
        if not path.exists():
            continue
        if rel.parts[0] not in ALLOWED_TOP:
            problems.append(f"{rel}: outside the allowed public layout")
        if path.suffix.lower() in AUDIO:
            problems.append(f"{rel}: audio files never go in the public repo")
        if path.name in BANNED_NAMES or path.name.startswith(".env"):
            problems.append(f"{rel}: secret-bearing file name")
        if rel.parts[0] == "media":
            if path.suffix.lower() not in MEDIA_EXT:
                problems.append(f"{rel}: media/ holds only final JPEG and MP4")
            if path.stat().st_size > MAX_MEDIA_BYTES:
                problems.append(f"{rel}: over {MAX_MEDIA_BYTES // 2**20} MB")
            continue
        data = path.read_bytes()
        if path.name != "verify_public.py":
            for pattern in SECRET_PATTERNS:
                if pattern.search(data):
                    problems.append(f"{rel}: looks like it contains a secret ({pattern.pattern[:18]!r})")
    return problems


def main():
    problems = scan(tracked_files())
    for problem in problems:
        print(f"BLOCKED: {problem}")
    print("public scan: clean" if not problems else f"public scan: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
