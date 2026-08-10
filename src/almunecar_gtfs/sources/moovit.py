"""Moovit — secondary reference, used for discrepancy detection only.

Moovit never wins a reconciliation against current operator or municipal data.
Its job here is to make us notice when our stop count, stop order or first and
last departures disagree with an independently-built dataset.

Nothing in this module reaches the canonical dataset. It feeds
:mod:`almunecar_gtfs.compare`, which writes ``docs/comparison.md``.

Moovit renders its pages with JavaScript and serves nothing useful to a plain
HTTP client, so these were read in a browser on 2026-08-10 and transcribed. A
dated manual transcription is more honest than a scraper that will silently
break.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

TRANSCRIBED_AT = dt.date(2026, 8, 10)


@dataclass(frozen=True)
class MoovitRoute:
    """A route as Moovit presents it."""

    route_label: str
    subtitle: str
    our_pattern_id: str | None
    """The canonical pattern this is being compared against, if any."""

    stop_names: tuple[str, ...] = ()
    first_departure: str | None = None
    last_departure: str | None = None
    trip_duration_minutes: int | None = None
    source_url: str | None = None
    notes: str | None = None

    @property
    def stop_count(self) -> int:
        return len(self.stop_names)


BASE = "https://moovitapp.com/index/en/public_transit-line"

ROUTES: tuple[MoovitRoute, ...] = (
    MoovitRoute(
        route_label="LÍNEA 1",
        subtitle="Circular",
        our_pattern_id="ALM_1_CIRC",
        stop_names=(
            "Plaza De La Carrera", "Plaza De Madrid", "Paseo Del Altillo",
            "Peñón Del Santo", "Hotel Almuñécar Playa", "Hotel Helios", "Mar Del Sol",
            "Chinasol", "Rinconcillo Jr", "Los Ramos", "Hotel Cotobro", "Los Ramos",
            "Rincón De La China (Retorno)", "Chinasol", "Los Marinos",
            "Puente De Noy 1", "Puente De Noy 2", "Costa Banana R",
            "Albaicin Del Mar R", "Avda Costa Del Sol R", "Plaza De La Carrera",
        ),
        trip_duration_minutes=19,
        source_url=f"{BASE}-l%C3%8Dnea_1-Granada-2422-2192113-42842824-0",
        notes="Still lists Paseo Del Altillo, which is closed to traffic since 2026-04-13.",
    ),
    MoovitRoute(
        route_label="LÍNEA 2 LA HERRADURA",
        subtitle="Almuñécar - La Herradura - Marina del Este",
        our_pattern_id="ALM_2B_CIRC_SUMMER",
        stop_names=(
            "Avda Costa Sol", "Albaicin Del Mar", "Costa Banana", "La Herradura",
            "Mercado La Herradura", "Paseo Andrés Segovia, Naúticas R",
            "Paseo Andrés Segovia, Windsurf R", "Mercado La Herradura R",
            "Plaza De La Carrera", "Paseo Andrés Segovia, Windsurf",
            "Paseo Andrés Segovia, Náuticas", "Peña Parda",
            "Paseo Andrés Segovia, Bar Bambú", "Paseo Andrés Segovia, La Caleta",
            "Paseo Andrés Segovia, Los Fenicios R", "Urb Punta De La Mona R",
            "Marina Del Este (Best Alcázar) R", "Puerto Dep. Marina Del Este",
            "Marina Del Este (Best Alcázar)", "Mirador De Cotobro R", "Costa Banana R",
            "Albaicin Del Mar R", "Avda Costa Del Sol R",
        ),
        first_departure="07:35",
        last_departure="20:30",
        trip_duration_minutes=33,
        source_url=f"{BASE}-l%C3%8Dnea_2_la_herradura-Granada-2422-2192113-67055103-0",
        notes=(
            "Moovit models 2A and 2B as one line. Its listed hours (Mon-Fri "
            "07:35-20:30) are the operator's *winter* times, read during summer, so "
            "Moovit appears to be a season behind."
        ),
    ),
    MoovitRoute(
        route_label="LÍNEA 3",
        subtitle="Velilla",
        our_pattern_id="ALM_3A_CIRC",
        stop_names=(
            "Plaza De La Carrera", "Estación De Autobuses De Almuñécar",
            "Avenida De Juan Carlos I", "Playa Puerta Del Mar", "Las Góndolas",
            "Paseo Reina Sofía", "Aquatropic", "Espigón", "Playa Tropical I",
            "Playa Tropical II", "Velilla I", "Velilla II", "Velilla III", "Velilla IV",
            "Pozuelo", "Playa Calida", "Barranco De Las Golondrinas",
            "Rambla Del Caballero", "Taramay", "Portichuelo", "La Paloma",
            "Plaza De La Carrera",
        ),
        first_departure="07:40",
        last_departure="20:30",
        trip_duration_minutes=20,
        source_url=f"{BASE}-l%C3%8Dnea_3-Granada-2422-2192113-42842826-0",
        notes="Moovit shows a single 'Línea 3'; the operator splits it into 3A, 3B and 3C.",
    ),
    MoovitRoute(
        route_label="LÍNEA 5",
        subtitle="Torrecuevas",
        our_pattern_id="ALM_TORRECUEVAS_CIRC",
        stop_names=(
            "Plaza De La Carrera", "Barrio De San Sebastián I",
            "Barrio De San Sebastián II", "Laderas De Castelar", "Peñuelas",
            "Venta Luciano", "Torrecuevas", "Arcos De Torrecuevas",
            "Cortijo Cahicillos", "Arcos De Torrecuevas", "Torrecuevas",
            "Venta Luciano", "Peñuelas", "Laderas De Castelar",
            "Barrio De San Sebastián II", "Barrio De San Sebastián I",
            "Plaza De La Carrera",
        ),
        first_departure="09:00",
        last_departure="19:15",
        trip_duration_minutes=18,
        source_url=f"{BASE}-l%C3%8Dnea_5-Granada-2422-2192113-42842827-0",
        notes=(
            "Third source calling Torrecuevas line 5. Not independent of OSM or of "
            "the operator's winter page: all three could be reading the same signage."
        ),
    ),
)

ROUTES_BY_PATTERN: dict[str, MoovitRoute] = {
    route.our_pattern_id: route for route in ROUTES if route.our_pattern_id
}
