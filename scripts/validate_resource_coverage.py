"""Development gate for CAT/GMAT resource coverage."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from adaptive import coverage_report


def run():
    with main.connection() as con:
        report = coverage_report(con)
    if not report["valid"]:
        raise SystemExit("Resource coverage failed:\n" + "\n".join(report["issues"]))
    print(
        f"Resource coverage passed: {report['topics_checked']} CAT topics and "
        f"{report['resources_checked']} active resources checked."
    )


if __name__ == "__main__":
    run()
