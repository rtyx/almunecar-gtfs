"""Command line entry point.

    uv run almunecar-gtfs reconcile   # evidence  -> data/canonical
    uv run almunecar-gtfs check       # canonical -> QA findings
    uv run almunecar-gtfs build       # canonical -> data/generated/gtfs + zip
    uv run almunecar-gtfs validate    # zip       -> MobilityData validator report
    uv run almunecar-gtfs map         # canonical -> qa/map.html
    uv run almunecar-gtfs conflicts   # evidence  -> docs/conflicts.md
    uv run almunecar-gtfs compare     # canonical -> docs/comparison.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from almunecar_gtfs import dataset, qa
from almunecar_gtfs import reconcile as reconcile_pkg
from almunecar_gtfs.compare import write_comparison_markdown
from almunecar_gtfs.conflicts_report import write_conflicts_markdown
from almunecar_gtfs.gtfs import build as build_mod
from almunecar_gtfs.gtfs import validate as validate_mod
from almunecar_gtfs.provenance import EvidenceStore, dump_conflicts
from almunecar_gtfs.qamap import write_qa_map
from almunecar_gtfs.sources.base import fetch
from almunecar_gtfs.sources.ingest import ingest

REPO_ROOT = Path(__file__).resolve().parents[2]

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    root = args.root.resolve()
    return root, root / "data" / "evidence", root / "data" / "canonical"


def _load_evidence(evidence_dir: Path) -> EvidenceStore:
    if not (evidence_dir / "sources.yaml").exists():
        raise SystemExit(
            f"{evidence_dir / 'sources.yaml'} not found. "
            f"Source acquisition has to happen before anything else can run."
        )
    return EvidenceStore.load(evidence_dir)


def cmd_ingest(args: argparse.Namespace) -> int:
    """Rebuild the evidence files from cached sources and transcriptions."""
    root, evidence_dir, _ = _paths(args)
    sources, observations = ingest(root / "data", refresh=args.refresh, offline=args.offline)
    print(f"wrote {sources} source(s) and {observations} observation(s) to {evidence_dir}")
    return EXIT_OK


def cmd_reconcile(args: argparse.Namespace) -> int:
    root, evidence_dir, canonical_dir = _paths(args)
    evidence = _load_evidence(evidence_dir)
    result = reconcile_pkg.reconcile(evidence, root / "data")

    dump_conflicts(evidence_dir / "conflicts.yaml", result.conflicts)
    dataset.write_network(canonical_dir, result.network)

    network = result.network
    print(
        f"canonical: {len(network.stops)} stops, {len(network.routes)} routes, "
        f"{len(network.patterns)} patterns, {len(network.trips)} trips, "
        f"{len(network.shapes)} shapes"
    )
    unresolved = [c for c in result.conflicts if c.status == "unresolved"]
    print(f"conflicts: {len(result.conflicts)} recorded, {len(unresolved)} unresolved")

    if result.problems:
        print(f"\n{len(result.problems)} reconciliation problem(s):", file=sys.stderr)
        for problem in result.problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    root, evidence_dir, canonical_dir = _paths(args)
    network = dataset.read_network(canonical_dir)
    evidence = _load_evidence(evidence_dir) if (evidence_dir / "sources.yaml").exists() else None
    findings = qa.check_all(network, evidence)

    for finding in findings:
        print(finding)
    errors = qa.errors(findings)
    warnings = qa.warnings(findings)
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    if errors:
        return EXIT_FINDINGS
    if warnings and args.strict:
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_build(args: argparse.Namespace) -> int:
    root, _, canonical_dir = _paths(args)
    network = dataset.read_network(canonical_dir)
    generated = root / "data" / "generated"
    try:
        feed = build_mod.build_feed(network)
    except build_mod.BuildError as error:
        print(f"build failed: {error}", file=sys.stderr)
        return EXIT_FINDINGS

    written = build_mod.write_feed(generated / "gtfs", feed)
    zip_path = build_mod.write_zip(generated / "almunecar-gtfs.zip", feed)
    for path in written:
        print(f"  {path.relative_to(root)}  {len(feed[path.name].splitlines()) - 1} row(s)")
    print(f"\n{zip_path.relative_to(root)}")

    missing = build_mod.REQUIRED_GTFS_FILES - set(feed)
    if missing:
        print(f"missing required file(s): {', '.join(sorted(missing))}", file=sys.stderr)
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    root, _, _ = _paths(args)
    zip_path = root / "data" / "generated" / "almunecar-gtfs.zip"
    output_dir = root / "qa" / "validation"
    try:
        report = validate_mod.validate(zip_path, output_dir, validator_jar=args.validator_jar)
    except validate_mod.ValidatorNotAvailable as error:
        print(str(error), file=sys.stderr)
        return EXIT_USAGE
    print(report.summary())
    print(f"\nreport: {report.report_path}")
    return EXIT_OK if report.is_release_ready else EXIT_FINDINGS


def cmd_map(args: argparse.Namespace) -> int:
    root, evidence_dir, canonical_dir = _paths(args)
    network = dataset.read_network(canonical_dir)
    evidence = _load_evidence(evidence_dir)
    output = root / "qa" / "map.html"
    write_qa_map(output, network, evidence, qa.check_all(network, evidence))
    print(f"wrote {output}")
    return EXIT_OK


def cmd_conflicts(args: argparse.Namespace) -> int:
    root, evidence_dir, _ = _paths(args)
    evidence = _load_evidence(evidence_dir)
    output = root / "docs" / "conflicts.md"
    unresolved = write_conflicts_markdown(output, evidence)
    print(f"wrote {output} ({unresolved} unresolved)")
    return EXIT_OK


def cmd_compare(args: argparse.Namespace) -> int:
    root, _, canonical_dir = _paths(args)
    network = dataset.read_network(canonical_dir)
    output = root / "docs" / "comparison.md"
    disagreements = write_comparison_markdown(output, network)
    print(f"wrote {output} ({disagreements} disagreement(s))")
    return EXIT_OK


def cmd_monitor(args: argparse.Namespace) -> int:
    """Re-fetch registered sources and report the ones whose content changed.

    Deliberately read-only with respect to canonical data: a changed webpage
    opens an issue for a human to review, it never rewrites the dataset.
    """
    root, evidence_dir, _ = _paths(args)
    evidence = _load_evidence(evidence_dir)
    cache_dir = root / "data" / "cache" / "monitor"

    changed: list[tuple[str, str, str]] = []
    unreachable: list[tuple[str, str]] = []
    for source_id, source in sorted(evidence.sources.items()):
        if source.source_type in ("moovit", "osm"):
            continue  # QA references, not authorities; not worth alerting on
        try:
            result = fetch(source.source_url, cache_dir, force=True)
        except Exception as error:  # noqa: BLE001 - a failed fetch is itself news
            unreachable.append((source_id, str(error)))
            continue
        if result.status_code != 200:
            unreachable.append((source_id, f"HTTP {result.status_code}"))
            continue
        if source.content_sha256 and source.content_sha256 != result.normalized_sha256:
            changed.append((source_id, source.source_url, result.normalized_sha256))
        elif not source.content_sha256:
            print(f"  {source_id}: no baseline hash recorded ({result.normalized_sha256})")

    for source_id, reason in unreachable:
        print(f"UNREACHABLE {source_id}: {reason}")
    for source_id, url, digest in changed:
        print(f"CHANGED {source_id} {url} new_normalized_sha256={digest}")

    print(f"\n{len(changed)} changed, {len(unreachable)} unreachable")
    return EXIT_FINDINGS if (changed or unreachable) else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="almunecar-gtfs",
        description="Source-backed GTFS for the Almunecar urban bus network.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (default: the installed package's repository)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest", help="rebuild data/evidence from cached sources"
    )
    ingest_parser.add_argument(
        "--refresh", action="store_true", help="re-fetch source pages instead of using the cache"
    )
    ingest_parser.add_argument(
        "--offline",
        action="store_true",
        help="do not fetch at all; keep the content hashes already in sources.yaml",
    )
    ingest_parser.set_defaults(func=cmd_ingest)

    subparsers.add_parser("reconcile", help="build canonical data from evidence").set_defaults(
        func=cmd_reconcile
    )

    check = subparsers.add_parser("check", help="run QA invariants over canonical data")
    check.add_argument("--strict", action="store_true", help="treat warnings as failures")
    check.set_defaults(func=cmd_check)

    subparsers.add_parser("build", help="generate GTFS files and zip").set_defaults(func=cmd_build)

    validate = subparsers.add_parser("validate", help="run the canonical GTFS validator")
    validate.add_argument("--validator-jar", type=Path, default=None)
    validate.set_defaults(func=cmd_validate)

    subparsers.add_parser("map", help="write the interactive QA map").set_defaults(func=cmd_map)
    subparsers.add_parser("conflicts", help="write docs/conflicts.md").set_defaults(
        func=cmd_conflicts
    )
    subparsers.add_parser(
        "compare", help="cross-check against Moovit and the operator's diagrams"
    ).set_defaults(func=cmd_compare)
    subparsers.add_parser(
        "monitor", help="re-fetch registered sources and report content changes"
    ).set_defaults(func=cmd_monitor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
