"""Dependency-free Python lint gate used by CI/local validation."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"node_modules", "static", "__pycache__"}


def main():
    failures = []
    files = [path for path in ROOT.rglob("*.py") if not EXCLUDED.intersection(path.parts)]
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeError) as error:
            failures.append(f"{path.relative_to(ROOT)}: {error}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Python lint passed ({len(files)} files parsed).")


if __name__ == "__main__":
    main()
