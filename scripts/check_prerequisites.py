"""Check local bootstrap tools without requiring optional cloud services."""
import importlib.util
import shutil
import sys


def main() -> int:
    print("Python:", sys.version.split()[0])
    if sys.version_info < (3, 11):
        print("FAIL: Python 3.11+ is required")
        return 1
    for tool in ("git", "docker", "code"):
        print(f"{tool}: {'available' if shutil.which(tool) else 'not found (optional for initial local smoke tests)' if tool != 'git' else 'not found (required for GitHub workflow)'}")
    for pkg in ("duckdb", "pytest", "data_platform", "ai_platform"):
        print(f"{pkg}: {'installed' if importlib.util.find_spec(pkg) else 'missing; run pip install -r requirements.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
