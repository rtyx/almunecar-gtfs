"""Evidence and provenance layer.

This module answers the first of the project's two questions: *what do the
available sources say?*

Nothing here decides what the network "really" is. Scrapers append
:class:`Observation` rows to ``data/evidence/observations.csv``; reconciliation
(see :mod:`almunecar_gtfs.reconcile`) reads them and produces canonical data.
Disagreements are preserved as :class:`Conflict` records rather than discarded.
"""

from __future__ import annotations

import csv
import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Confidence(StrEnum):
    """How much weight a single observation carries."""

    CONFIRMED = "confirmed"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNRESOLVED = "unresolved"


#: Higher is better. ``unresolved`` deliberately scores below everything else so
#: that it can never win a reconciliation on its own.
CONFIDENCE_ORDER: dict[Confidence, int] = {
    Confidence.CONFIRMED: 4,
    Confidence.HIGH: 3,
    Confidence.MEDIUM: 2,
    Confidence.LOW: 1,
    Confidence.UNRESOLVED: 0,
}


class SourceType(StrEnum):
    """Where a claim came from, coarsely."""

    OFFICIAL = "official"
    """Autocares Urbanos Almunecar / Roalfa, current website or printed material."""

    MUNICIPAL = "municipal"
    """Ayuntamiento de Almunecar documents, GIS, ordinances."""

    IBUSGPS = "ibusgps"
    """The iBusGPS passenger information system."""

    MOOVIT = "moovit"
    """Moovit. Secondary reference only; never authoritative against the operator."""

    OSM = "osm"
    """OpenStreetMap."""

    FIELD = "field"
    """Direct on-the-ground observation (photograph of a pole, a ridden trip)."""

    DERIVED = "derived"
    """Computed from other observations. Must record its derivation method."""


class EvidenceKind(StrEnum):
    """What *sort* of evidence a source offered.

    The source hierarchy is not purely by source: an explicit platform coordinate
    published by the operator outranks a pin dropped on a map by the same
    operator, and a restaurant's POI coordinate is not stop evidence at all.
    """

    STOP_COORDINATE = "stop_coordinate"
    """An explicit bus-stop / platform coordinate."""

    MAP_PIN = "map_pin"
    """A pin on an official map, positioned deliberately but without a stated datum."""

    GIS = "gis"
    """A municipal GIS layer or surveyed dataset."""

    BUS_STOP_NODE = "bus_stop_node"
    """OSM ``highway=bus_stop`` / ``public_transport=platform``, verified."""

    POI = "poi"
    """An ordinary point of interest (hotel, restaurant, beach) that merely shares a name."""

    TIMETABLE = "timetable"
    """A published timetable."""

    NARRATIVE = "narrative"
    """Prose on a webpage, a news article, a social media post."""

    RESEARCH = "research"
    """Manually researched, e.g. read off satellite imagery or street level photos."""

    TRACE = "trace"
    """Recorded vehicle movement."""


class EvidenceDomain(StrEnum):
    """Field families that each have their own source hierarchy."""

    SCHEDULE = "schedule"
    """Route names, service periods, published departures."""

    STOP_COORD = "stop_coord"
    """Stop positions."""

    GEOMETRY = "geometry"
    """Route shapes."""


def _tier(source_type: SourceType, kind: EvidenceKind | None = None) -> str:
    return f"{source_type}:{kind}" if kind is not None else str(source_type)


#: Ordered best-first. An entry is either ``"<source_type>"`` (any evidence kind)
#: or ``"<source_type>:<evidence_kind>"`` (more specific, checked first).
HIERARCHIES: dict[EvidenceDomain, tuple[str, ...]] = {
    EvidenceDomain.SCHEDULE: (
        _tier(SourceType.OFFICIAL),
        _tier(SourceType.MUNICIPAL),
        _tier(SourceType.IBUSGPS),
        _tier(SourceType.MOOVIT),
        _tier(SourceType.OSM),
        # Below every real source: a derived value should yield the moment any
        # source actually publishes the fact.
        _tier(SourceType.DERIVED),
    ),
    EvidenceDomain.STOP_COORD: (
        _tier(SourceType.OFFICIAL, EvidenceKind.STOP_COORDINATE),
        _tier(SourceType.IBUSGPS, EvidenceKind.STOP_COORDINATE),
        _tier(SourceType.OFFICIAL, EvidenceKind.MAP_PIN),
        _tier(SourceType.MUNICIPAL, EvidenceKind.GIS),
        _tier(SourceType.MUNICIPAL),
        _tier(SourceType.OSM, EvidenceKind.BUS_STOP_NODE),
        _tier(SourceType.FIELD),
        _tier(SourceType.MOOVIT),
        _tier(SourceType.OSM),
        _tier(SourceType.DERIVED, EvidenceKind.RESEARCH),
    ),
    EvidenceDomain.GEOMETRY: (
        _tier(SourceType.IBUSGPS),
        _tier(SourceType.OFFICIAL),
        _tier(SourceType.FIELD, EvidenceKind.TRACE),
        _tier(SourceType.MUNICIPAL),
        _tier(SourceType.OSM),
        _tier(SourceType.DERIVED),
    ),
}

#: Evidence that may never *by itself* establish a fact in a given domain.
#: "Never use an ordinary POI coordinate as evidence for a stop without
#: additional confirmation."
DISQUALIFIED: dict[EvidenceDomain, frozenset[tuple[SourceType | None, EvidenceKind]]] = {
    EvidenceDomain.STOP_COORD: frozenset({(None, EvidenceKind.POI)}),
}

#: Rank returned for evidence that matches no tier: worse than every known tier.
UNRANKED = 10_000


def rank(domain: EvidenceDomain, source_type: SourceType, kind: EvidenceKind | None) -> int:
    """Position of this evidence in ``domain``'s hierarchy. Lower is better."""
    tiers = HIERARCHIES[domain]
    specific = _tier(source_type, kind) if kind is not None else None
    for index, tier in enumerate(tiers):
        if specific is not None and tier == specific:
            return index
        if tier == str(source_type):
            return index
    return UNRANKED


def is_disqualified(
    domain: EvidenceDomain, source_type: SourceType, kind: EvidenceKind | None
) -> bool:
    """Whether this evidence needs corroboration before it can establish a fact."""
    if kind is None:
        return False
    for banned_source, banned_kind in DISQUALIFIED.get(domain, frozenset()):
        if banned_kind == kind and banned_source in (None, source_type):
            return True
    return False


class Source(BaseModel):
    """A registered origin of claims, described once in ``sources.yaml``."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: SourceType
    source_url: str
    title: str
    retrieved_at: dt.date | None = None
    """When the source was last consulted. Individual observations may override."""

    content_sha256: str | None = None
    """Normalised content hash, used by source-change monitoring."""

    authoritative_until: dt.date | None = None
    """Set when a page is known to be stale (e.g. a superseded seasonal timetable)."""

    license: str | None = None
    notes: str | None = None

    @property
    def is_stale(self) -> bool:
        return self.authoritative_until is not None and self.authoritative_until < dt.date.today()


class Observation(BaseModel):
    """One claim, by one source, about one field of one entity."""

    model_config = ConfigDict(extra="forbid")

    entity: str
    """Namespaced key, e.g. ``route:2B``, ``stop:ALM_0001``, ``pattern:ALM_2B_OUT_SUMMER``."""

    field: str
    value: str
    """Always stored as text. Typed parsing happens during reconciliation."""

    source_id: str
    retrieved_at: dt.date
    confidence: Confidence = Confidence.MEDIUM
    evidence_kind: EvidenceKind | None = None
    source_url: str | None = None
    """Deep link to the exact page/section, when the source is a whole site."""

    derivation: str | None = None
    """Required for ``derived`` observations: how the value was computed."""

    derived_from: str | None = None
    """``;``-separated source ids the derivation consumed."""

    sample_size: int | None = None
    """Number of underlying observations behind a median or average."""

    notes: str | None = None

    @field_validator("entity")
    @classmethod
    def _entity_is_namespaced(cls, value: str) -> str:
        if ":" not in value:
            raise ValueError(f"entity must be namespaced as '<type>:<id>', got {value!r}")
        return value

    @property
    def derived_source_ids(self) -> list[str]:
        if not self.derived_from:
            return [self.source_id]
        return [item.strip() for item in self.derived_from.split(";") if item.strip()]

    @property
    def entity_type(self) -> str:
        return self.entity.split(":", 1)[0]

    @property
    def entity_id(self) -> str:
        return self.entity.split(":", 1)[1]


CSV_COLUMNS: tuple[str, ...] = (
    "entity",
    "field",
    "value",
    "source_id",
    "retrieved_at",
    "confidence",
    "evidence_kind",
    "source_url",
    "derivation",
    "derived_from",
    "sample_size",
    "notes",
)


class Claim(BaseModel):
    """One side of a recorded disagreement."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    value: str
    retrieved_at: dt.date
    confidence: Confidence
    notes: str | None = None


class Conflict(BaseModel):
    """A disagreement between sources, preserved whether or not it is resolved.

    Reconciliation never deletes these. A resolved conflict keeps every original
    claim so that a future reviewer can see what was rejected and why.
    """

    model_config = ConfigDict(extra="forbid")

    entity: str
    field: str
    claims: list[Claim] = Field(min_length=2)
    status: str = "unresolved"
    """``unresolved`` | ``resolved`` | ``accepted_ambiguity``."""

    resolution: str | None = None
    """Prose explaining the decision. Required once status is ``resolved``."""

    resolved_value: str | None = None
    resolved_at: dt.date | None = None
    blocks_publication: bool = False
    """True when the affected entity must not be published until this is settled."""

    @property
    def key(self) -> tuple[str, str]:
        return (self.entity, self.field)


class EvidenceStore:
    """In-memory view of ``data/evidence``."""

    def __init__(
        self,
        sources: Iterable[Source] = (),
        observations: Iterable[Observation] = (),
        conflicts: Iterable[Conflict] = (),
    ) -> None:
        self.sources: dict[str, Source] = {s.source_id: s for s in sources}
        self.observations: list[Observation] = list(observations)
        self.conflicts: list[Conflict] = list(conflicts)
        self._validate_source_references()

    # -- loading ---------------------------------------------------------

    @classmethod
    def load(cls, evidence_dir: Path) -> EvidenceStore:
        return cls(
            sources=load_sources(evidence_dir / "sources.yaml"),
            observations=load_observations(evidence_dir / "observations.csv"),
            conflicts=load_conflicts(evidence_dir / "conflicts.yaml"),
        )

    def _validate_source_references(self) -> None:
        unknown = sorted(
            {o.source_id for o in self.observations if o.source_id not in self.sources}
        )
        if unknown:
            raise ValueError(
                "observations reference unregistered source_id(s): " + ", ".join(unknown)
            )

    # -- querying --------------------------------------------------------

    def __iter__(self) -> Iterator[Observation]:
        return iter(self.observations)

    def source_of(self, observation: Observation) -> Source:
        return self.sources[observation.source_id]

    def for_field(self, entity: str, field: str) -> list[Observation]:
        return [o for o in self.observations if o.entity == entity and o.field == field]

    def entities(self, entity_type: str) -> list[str]:
        seen = {o.entity for o in self.observations if o.entity_type == entity_type}
        return sorted(seen)

    def fields_by_entity(self) -> dict[str, set[str]]:
        grouped: dict[str, set[str]] = defaultdict(set)
        for observation in self.observations:
            grouped[observation.entity].add(observation.field)
        return dict(grouped)

    def conflict_for(self, entity: str, field: str) -> Conflict | None:
        for conflict in self.conflicts:
            if conflict.key == (entity, field):
                return conflict
        return None

    def blocking_entities(self) -> set[str]:
        """Entities that an unsettled, publication-blocking conflict makes unpublishable."""
        return {
            c.entity
            for c in self.conflicts
            if c.blocks_publication and c.status == "unresolved"
        }

    def blocked_fields(self) -> set[tuple[str, str]]:
        """``(entity, field)`` pairs where an unsettled dispute blocks publication.

        Reconciliation refuses to produce a value for these. The alternative is
        worse than having no value: with two equally-ranked claims the ordering
        falls through to the source id, so the dataset would report whichever
        source happens to sort first as though it had been chosen.
        """
        return {
            c.key
            for c in self.conflicts
            if c.blocks_publication and c.status == "unresolved"
        }

    # -- ordering --------------------------------------------------------

    def sort_key(self, domain: EvidenceDomain, observation: Observation) -> tuple:
        """Best-first ordering key for observations competing over one field.

        Hierarchy position dominates confidence: a medium-confidence operator
        page still beats a high-confidence Moovit page, because the operator is
        the authority on its own network. Recency breaks remaining ties, so a
        current operator page wins over a stale one.
        """
        source = self.sources[observation.source_id]
        return (
            is_disqualified(domain, source.source_type, observation.evidence_kind),
            source.is_stale,
            rank(domain, source.source_type, observation.evidence_kind),
            -CONFIDENCE_ORDER[observation.confidence],
            -observation.retrieved_at.toordinal(),
            observation.source_id,
        )

    def ranked(self, domain: EvidenceDomain, entity: str, field: str) -> list[Observation]:
        return sorted(self.for_field(entity, field), key=lambda o: self.sort_key(domain, o))

    def best(self, domain: EvidenceDomain, entity: str, field: str) -> Observation | None:
        """The observation that should establish this field, or ``None``.

        Returns ``None`` when the only available evidence is disqualified and
        uncorroborated, rather than silently promoting it.
        """
        if (entity, field) in self.blocked_fields():
            # An unsettled, publication-blocking dispute has no winner. Returning
            # the top-ranked claim here would dress a tie-break up as a decision.
            return None
        candidates = self.ranked(domain, entity, field)
        if not candidates:
            return None
        winner = candidates[0]
        source = self.sources[winner.source_id]
        if is_disqualified(domain, source.source_type, winner.evidence_kind):
            return None
        return winner

    # -- conflict detection ----------------------------------------------

    def detect_conflicts(self, domain_for: DomainResolver) -> list[Conflict]:
        """Every (entity, field) where registered sources state different values."""
        grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
        for observation in self.observations:
            grouped[(observation.entity, observation.field)].append(observation)

        found: list[Conflict] = []
        for (entity, field), observations in sorted(grouped.items()):
            values = {o.value for o in observations}
            if len(values) < 2:
                continue
            domain = domain_for(entity, field)
            ordered = sorted(observations, key=lambda o: self.sort_key(domain, o))
            found.append(
                Conflict(
                    entity=entity,
                    field=field,
                    claims=[
                        Claim(
                            source_id=o.source_id,
                            value=o.value,
                            retrieved_at=o.retrieved_at,
                            confidence=o.confidence,
                            notes=o.notes,
                        )
                        for o in ordered
                    ],
                )
            )
        return found


class DomainResolver:
    """Callable mapping ``(entity, field)`` to its :class:`EvidenceDomain`."""

    def __call__(self, entity: str, field: str) -> EvidenceDomain:  # pragma: no cover - protocol
        raise NotImplementedError


# -- file IO -------------------------------------------------------------


def load_sources(path: Path) -> list[Source]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [Source.model_validate(item) for item in raw]


def dump_sources(path: Path, sources: Sequence[Source]) -> None:
    ordered = sorted(sources, key=lambda s: s.source_id)
    payload = [s.model_dump(mode="json", exclude_none=True) for s in ordered]
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def load_observations(path: Path) -> list[Observation]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    observations: list[Observation] = []
    for line_number, row in enumerate(rows, start=2):
        cleaned = {k: (v if v not in ("", None) else None) for k, v in row.items()}
        cleaned.pop(None, None)
        try:
            observations.append(Observation.model_validate(cleaned))
        except Exception as error:  # noqa: BLE001 - re-raised with location
            raise ValueError(f"{path}:{line_number}: {error}") from error
    return observations


def dump_observations(path: Path, observations: Sequence[Observation]) -> None:
    """Write observations in a stable order so diffs stay reviewable."""
    ordered = sorted(
        observations, key=lambda o: (o.entity, o.field, o.source_id, o.retrieved_at)
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for observation in ordered:
            row = observation.model_dump(mode="json")
            writer.writerow({column: row.get(column) or "" for column in CSV_COLUMNS})


def load_conflicts(path: Path) -> list[Conflict]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [Conflict.model_validate(item) for item in raw]


def dump_conflicts(path: Path, conflicts: Sequence[Conflict]) -> None:
    ordered = sorted(conflicts, key=lambda c: c.key)
    payload = [c.model_dump(mode="json", exclude_none=True) for c in ordered]
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def merge_conflicts(
    existing: Sequence[Conflict], detected: Sequence[Conflict]
) -> list[Conflict]:
    """Fold newly detected conflicts into the hand-curated file.

    Human resolutions are never overwritten; a resolved conflict whose claims
    have changed is reopened rather than silently kept closed.
    """
    by_key = {c.key: c for c in existing}
    merged: list[Conflict] = []
    for conflict in detected:
        previous = by_key.pop(conflict.key, None)
        if previous is None:
            merged.append(conflict)
            continue
        claims_changed = [c.model_dump() for c in previous.claims] != [
            c.model_dump() for c in conflict.claims
        ]
        if claims_changed and previous.status == "resolved":
            merged.append(
                conflict.model_copy(
                    update={
                        "status": "unresolved",
                        "resolution": (
                            f"REOPENED: source claims changed after resolution "
                            f"({previous.resolved_at}). Previous decision: {previous.resolution}"
                        ),
                        "blocks_publication": previous.blocks_publication,
                    }
                )
            )
        else:
            merged.append(previous.model_copy(update={"claims": conflict.claims}))
    # Conflicts that no longer reproduce are kept, marked so, never deleted.
    for orphan in by_key.values():
        if orphan.status == "unresolved":
            orphan = orphan.model_copy(
                update={
                    "status": "accepted_ambiguity",
                    "resolution": "No longer reproducible from current evidence; kept for history.",
                }
            )
        merged.append(orphan)
    return sorted(merged, key=lambda c: c.key)
