"""Generate a PBKDF2 password hash for VERITYFORGE_USERS.

Usage:
  python apps/cli/hash_password.py [username]
Prompts for the password (hidden), prints the entry to put in VERITYFORGE_USERS:
  alice:pbkdf2_sha256$200000$...$...
Combine multiple users with commas.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from verityforge.auth import hash_password  # noqa: E402


def main() -> int:
    user = sys.argv[1] if len(sys.argv) > 1 else input("username: ").strip()
    pw = getpass.getpass("password: ")
    if pw != getpass.getpass("confirm:  "):
        print("passwords do not match", file=sys.stderr)
        return 1
    print(f"\n{user}:{hash_password(pw)}")
    print("\nAdd to .env as VERITYFORGE_USERS (comma-separate multiple users).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
