"""Wrapper around the MobilityData Canonical GTFS Schedule Validator.

The jar is never downloaded automatically. Point ``GTFS_VALIDATOR_JAR`` at a
copy you have obtained yourself, or pass ``--validator-jar``; CI fetches it
explicitly in ``.github/workflows/validate-gtfs.yml`` where the download is
visible and reviewable.

Release criterion: zero validator errors. Warnings are kept as an artifact and
reviewed rather than suppressed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

VALIDATOR_ENV_VAR = "GTFS_VALIDATOR_JAR"
VALIDATOR_HOMEPAGE = "https://github.com/MobilityData/gtfs-validator/releases"


class ValidatorNotAvailable(RuntimeError):
    """The validator jar or a Java runtime could not be found."""


@dataclass(frozen=True)
class Notice:
    code: str
    severity: str
    total: int
    samples: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationReport:
    notices: list[Notice]
    report_path: Path
    html_report_path: Path | None = None

    @property
    def errors(self) -> list[Notice]:
        return [n for n in self.notices if n.severity.upper() == "ERROR"]

    @property
    def warnings(self) -> list[Notice]:
        return [n for n in self.notices if n.severity.upper() == "WARNING"]

    @property
    def error_count(self) -> int:
        return sum(n.total for n in self.errors)

    @property
    def warning_count(self) -> int:
        return sum(n.total for n in self.warnings)

    @property
    def is_release_ready(self) -> bool:
        return self.error_count == 0

    def summary(self) -> str:
        lines = [f"{self.error_count} error(s), {self.warning_count} warning(s)"]
        for notice in sorted(self.errors + self.warnings, key=lambda n: (n.severity, n.code)):
            lines.append(f"  {notice.severity:8} {notice.code} x{notice.total}")
        return "\n".join(lines)


def find_validator_jar(explicit: Path | None = None) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise ValidatorNotAvailable(f"validator jar not found at {explicit}")
        return explicit
    from_env = os.environ.get(VALIDATOR_ENV_VAR)
    if from_env:
        path = Path(from_env)
        if not path.exists():
            raise ValidatorNotAvailable(
                f"{VALIDATOR_ENV_VAR} points at {path}, which does not exist"
            )
        return path
    raise ValidatorNotAvailable(
        "No GTFS validator jar configured.\n"
        f"Download one from {VALIDATOR_HOMEPAGE} and either set {VALIDATOR_ENV_VAR} "
        "or pass --validator-jar."
    )


def parse_report(report_path: Path) -> list[Notice]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    notices = []
    for item in payload.get("notices", []):
        notices.append(
            Notice(
                code=item.get("code", "unknown"),
                severity=item.get("severity", "UNKNOWN"),
                total=int(item.get("totalNotices", 0)),
                samples=item.get("sampleNotices", []),
            )
        )
    return notices


def validate(
    feed_zip: Path,
    output_dir: Path,
    validator_jar: Path | None = None,
    country_code: str = "es",
    extra_args: Sequence[str] = (),
) -> ValidationReport:
    """Run the validator over ``feed_zip`` and parse its JSON report."""
    jar = find_validator_jar(validator_jar)
    java = shutil.which("java")
    if java is None:
        raise ValidatorNotAvailable("java not found on PATH; the validator needs a JRE")
    if not feed_zip.exists():
        raise FileNotFoundError(f"{feed_zip} does not exist; run `almunecar-gtfs build` first")

    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        java,
        "-jar",
        str(jar),
        "--input",
        str(feed_zip),
        "--output_base",
        str(output_dir),
        "--country_code",
        country_code,
        *extra_args,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    report_path = output_dir / "report.json"
    if not report_path.exists():
        raise RuntimeError(
            "validator produced no report.json\n"
            f"exit code: {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    html_report = output_dir / "report.html"
    return ValidationReport(
        notices=parse_report(report_path),
        report_path=report_path,
        html_report_path=html_report if html_report.exists() else None,
    )
