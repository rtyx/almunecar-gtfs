"""Autocares Urbanos Almuñécar / Roalfa — the operator's own material.

Top of the hierarchy for route names, service periods and published departures.

**The operator publishes every timetable as an image**, not as text. There is no
markup to parse, so the departure times below were read off those images by hand
on 2026-08-10 and each records the exact image URL it came from. The images
themselves are not committed (they are cached under the git-ignored
``data/cache/``); only the facts are.

Two things the pages make explicit and that the dataset must not smooth over:

* the Torrecuevas line number differs between the summer page (``LINEA 4``) and
  the winter page (``Línea 5``), and both were last modified on the same day;
* the summer Torrecuevas page's own body text says "Vigencia del horario de
  *invierno* desde el 1 julio", which is a copy-paste error and a reason to
  treat that page's other details with care.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from almunecar_gtfs.sources.base import FetchResult, fetch

#: When the pages below were read and the timetable images transcribed.
TRANSCRIBED_AT = dt.date(2026, 8, 10)

BASE = "https://urbanosalmunecar.es"


@dataclass(frozen=True)
class OperatorPage:
    source_id: str
    url: str
    title: str
    covers: str
    """What the page is evidence about."""

    lastmod: dt.date | None = None
    """``<lastmod>`` from the site's own sitemap, not our retrieval date."""


#: Confirmed operator pages. Every one has been fetched successfully (HTTP 200)
#: and the ``lastmod`` values come from ``/wp-sitemap-posts-page-1.xml``.
PAGES: tuple[OperatorPage, ...] = (
    OperatorPage(
        "official_index",
        f"{BASE}/lineas-urbanas-almunecar/",
        "Líneas urbanas Almuñécar",
        "route inventory",
        dt.date(2021, 6, 16),
    ),
    OperatorPage(
        "official_l1_summer",
        f"{BASE}/lineas-urbanas-almunecar/circular-verano/",
        "Línea 1 Circular verano",
        "line 1 summer timetable and diversion notice",
        dt.date(2026, 7, 3),
    ),
    OperatorPage(
        "official_l1_winter",
        f"{BASE}/lineas-urbanas-almunecar/almunecar-circular-linea-1-invierno/",
        "Línea 1 Circular invierno",
        "line 1 winter timetable and roadworks notice",
        dt.date(2026, 5, 14),
    ),
    OperatorPage(
        "official_l2_summer",
        f"{BASE}/lineas-urbanas-almunecar/la-herradura-verano/",
        "Línea 2 La Herradura verano",
        "lines 2A and 2B summer timetables and route diagrams",
        dt.date(2026, 7, 3),
    ),
    OperatorPage(
        "official_l2_winter",
        f"{BASE}/lineas-urbanas-almunecar/la-herradura-linea-2-invierno/",
        "Línea 2 La Herradura invierno",
        "lines 2A and 2B winter timetables; Marina del Este not served in winter",
        dt.date(2026, 5, 14),
    ),
    OperatorPage(
        "official_l3a_summer",
        f"{BASE}/lineas-urbanas-almunecar/velilla-taramay-verano/",
        "Línea 3A Velilla–Taramay verano",
        "line 3A summer timetable",
        dt.date(2026, 7, 3),
    ),
    OperatorPage(
        "official_l3a_winter",
        f"{BASE}/lineas-urbanas-almunecar/velilla-taramay-invierno/",
        "Línea 3A Velilla–Taramay invierno",
        "line 3A winter timetable",
        dt.date(2026, 5, 14),
    ),
    OperatorPage(
        "official_l3b_summer",
        f"{BASE}/lineas-urbanas-almunecar/velilla-verano/",
        "Línea 3B Velilla verano",
        "line 3B summer-only timetable and Cabria extension notice",
        dt.date(2026, 7, 3),
    ),
    OperatorPage(
        "official_l3c_summer",
        f"{BASE}/lineas-urbanas-almunecar/taramay-verano/",
        "Línea 3C Taramay verano",
        "line 3C summer-only timetable",
        dt.date(2026, 7, 3),
    ),
    OperatorPage(
        "official_torrecuevas_summer",
        f"{BASE}/lineas-urbanas-almunecar/torrecuevas-verano/",
        "Línea Torrecuevas verano",
        "Torrecuevas summer timetable; body text says LINEA 4",
        dt.date(2026, 5, 14),
    ),
    OperatorPage(
        "official_torrecuevas_winter",
        f"{BASE}/lineas-urbanas-almunecar/torrecuevas-linea-5-invierno/",
        "Línea 5 Torrecuevas invierno",
        "Torrecuevas winter timetable; title and URL say Línea 5",
        dt.date(2026, 5, 14),
    ),
)

PAGES_BY_ID: dict[str, OperatorPage] = {page.source_id: page for page in PAGES}


@dataclass(frozen=True)
class Timetable:
    """Departure times from the principal stop, as printed on one image.

    The operator states this explicitly on nearly every page: *"LOS HORARIOS
    INDICAN LA HORA DE SALIDA DESDE LA PARADA PRINCIPAL"*. These are origin
    departures, not times at intermediate stops.
    """

    route_id: str
    season: str
    service_id: str
    departures: tuple[str, ...]
    source_id: str
    image_url: str
    note: str | None = None


IMG = f"{BASE}/wp-content/uploads"

#: Transcribed 2026-08-10. Each tuple is the printed list, in printed order.
TIMETABLES: tuple[Timetable, ...] = (
    # ---- Line 1 Circular -------------------------------------------------
    Timetable(
        "ALM_1", "summer", "SUMMER_MONSAT",
        ("8:30", "9:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
         "13:00", "14:00", "17:00", "18:00", "19:00", "20:00", "21:00", "22:00"),
        "official_l1_summer", f"{IMG}/2025/08/domingo-y-festivos-circular-ok-pica.png",
    ),
    Timetable(
        "ALM_1", "summer", "SUMMER_SUNHOL",
        ("8:30", "9:30", "10:30", "12:45", "17:00", "18:45", "21:00"),
        "official_l1_summer", f"{IMG}/2025/08/domingo-y-festivos-circular-ok-pica.png",
    ),
    Timetable(
        "ALM_1", "winter", "WINTER_MONSAT",
        ("8:30", "9:30", "10:00", "11:00", "11:30", "12:00", "12:30",
         "13:00", "14:00", "17:00", "18:00", "19:00", "20:00"),
        "official_l1_winter", f"{IMG}/2022/09/linea-1-almunecar-correcta.png",
    ),
    Timetable(
        "ALM_1", "winter", "WINTER_SUNHOL",
        ("8:30", "10:30", "12:45", "16:30", "18:45"),
        "official_l1_winter", f"{IMG}/2022/09/linea-1-almunecar-correcta.png",
        note="Printed as 'Domingo' only; whether public holidays are included is not stated.",
    ),
    # ---- Line 2A ---------------------------------------------------------
    Timetable(
        "ALM_2A", "summer", "SUMMER_MONFRI", ("8:00", "11:40"),
        "official_l2_summer", f"{IMG}/2025/08/horarios-2-a-ok-subir.png",
    ),
    Timetable(
        "ALM_2A", "summer", "SUMMER_SAT", ("8:00",),
        "official_l2_summer", f"{IMG}/2025/08/horarios-2-a-ok-subir.png",
        note="Sundays and holidays: sin servicio.",
    ),
    Timetable(
        "ALM_2A", "winter", "WINTER_MONFRI", ("7:35", "11:40"),
        "official_l2_winter", f"{IMG}/2022/09/image-3.png",
    ),
    Timetable(
        "ALM_2A", "winter", "WINTER_SAT", ("8:00",),
        "official_l2_winter", f"{IMG}/2022/09/image-3.png",
        note="Sundays: sin servicio.",
    ),
    # ---- Line 2B ---------------------------------------------------------
    Timetable(
        "ALM_2B", "summer", "SUMMER_MONSAT",
        ("10:30", "12:30", "16:30", "20:30", "21:30"),
        "official_l2_summer", f"{IMG}/2022/06/image-7.png",
        note=(
            "Printed as the unmarked row. A second row on the same image is "
            "labelled '* BAJADA PUERTO' with different times; which of the two "
            "actually descends to Marina del Este is not stated. See conflicts.yaml."
        ),
    ),
    Timetable(
        "ALM_2B", "summer", "SUMMER_MONSAT_PUERTO",
        ("8:45", "14:00", "17:30", "19:00"),
        "official_l2_summer", f"{IMG}/2022/06/image-7.png",
        note="Printed as '* BAJADA PUERTO'.",
    ),
    Timetable(
        "ALM_2B", "summer", "SUMMER_SUNHOL_PUERTO",
        ("8:50", "11:30", "13:15", "17:30", "19:45"),
        "official_l2_summer", f"{IMG}/2022/06/image-7.png",
        note="Printed as '* BAJADA PUERTO'; no unmarked Sunday row is shown.",
    ),
    Timetable(
        "ALM_2B", "winter", "WINTER_MONSAT",
        ("8:45", "10:30", "12:30", "14:00", "16:30", "17:30", "19:00", "20:30"),
        "official_l2_winter", f"{IMG}/2022/09/image-5.png",
        note="Single undivided row; the summer BAJADA PUERTO split does not appear.",
    ),
    Timetable(
        "ALM_2B", "winter", "WINTER_SUNHOL",
        ("8:50", "11:30", "13:15", "17:30", "19:45"),
        "official_l2_winter", f"{IMG}/2022/09/image-5.png",
    ),
    # ---- Line 3A ---------------------------------------------------------
    Timetable(
        "ALM_3A", "summer", "SUMMER_MONSAT", ("8:00", "16:30"),
        "official_l3a_summer", f"{IMG}/2022/06/image-10.png",
        note="Sundays and holidays: sin servicio. 3B and 3C cover Velilla and Taramay in summer.",
    ),
    Timetable(
        "ALM_3A", "winter", "WINTER_MONSAT",
        ("7:35", "9:30", "10:00", "11:30", "12:15", "13:30", "16:30", "17:30",
         "18:20", "20:00"),
        "official_l3a_winter", f"{IMG}/2022/09/image-6.png",
        note=(
            "Footnotes on the image: 7:35 runs from 8:00 on Saturdays; "
            "12:15 runs Monday to Friday only. Both need their own service periods."
        ),
    ),
    Timetable(
        "ALM_3A", "winter", "WINTER_SUNHOL",
        ("10:00", "12:15", "14:15", "18:15", "20:30"),
        "official_l3a_winter", f"{IMG}/2022/09/image-6.png",
    ),
    # ---- Line 3B (summer only) -------------------------------------------
    Timetable(
        "ALM_3B", "summer", "SUMMER_SUNHOL",
        ("9:00", "10:00", "11:00", "12:00", "13:00", "14:00", "18:00", "19:00",
         "20:00", "21:00"),
        "official_l3b_summer", f"{IMG}/2022/06/image-1.png",
        note=(
            "At 10:00, 12:00, 18:00 and 20:00 the image marks '* paradas ampliadas' "
            "and '** paradas no realizadas' — a different stop set on those runs."
        ),
    ),
    # ---- Line 3C (summer only) -------------------------------------------
    Timetable(
        "ALM_3C", "summer", "SUMMER_MONSAT",
        ("9:30", "11:30", "13:30", "17:30", "18:20", "20:00", "21:00"),
        "official_l3c_summer", f"{IMG}/2022/06/image-11.png",
        note="Sundays and holidays: sin servicio.",
    ),
    # ---- Torrecuevas -----------------------------------------------------
    Timetable(
        "ALM_TORRECUEVAS", "summer", "SUMMER_MONSAT",
        ("9:00", "10:00", "12:00", "13:30", "17:00", "18:30", "19:30", "20:30"),
        "official_torrecuevas_summer", f"{IMG}/2022/06/image-8.png",
    ),
    Timetable(
        "ALM_TORRECUEVAS", "summer", "SUMMER_SUNHOL",
        ("9:30", "11:00", "14:00", "17:00", "19:15"),
        "official_torrecuevas_summer", f"{IMG}/2022/06/image-8.png",
    ),
    Timetable(
        "ALM_TORRECUEVAS", "winter", "WINTER_MONSAT",
        ("9:00", "10:30", "12:00", "13:30", "17:00", "18:30", "19:30"),
        "official_torrecuevas_winter", f"{IMG}/2022/09/image-7.png",
    ),
    Timetable(
        "ALM_TORRECUEVAS", "winter", "WINTER_SUNHOL",
        ("9:30", "11:00", "13:50", "17:00", "19:15"),
        "official_torrecuevas_winter", f"{IMG}/2022/09/image-7.png",
    ),
)

#: Line 3B's Monday-to-Saturday summer service is printed as a frequency rather
#: than a list: "cada 30 min desde las 8:30 hasta 14:30 y desde 17:00 hasta 0:30".
#: Expanding it into departures is an interpretation, not a transcription, so it
#: is kept as prose here and recorded as an unresolved item rather than a list of
#: times we would then present as published.
LINE_3B_FREQUENCY_TEXT = (
    "Este servicio saldrá de su parada principal cada 30 min desde las 8:30 "
    "hasta 14:30 y desde 17:00 hasta 0:30"
)


@dataclass(frozen=True)
class Notice:
    """A dated operational notice printed on a page."""

    source_id: str
    subject: str
    text: str
    affects: tuple[str, ...] = ()
    starts: dt.date | None = None
    ends: dt.date | None = None


NOTICES: tuple[Notice, ...] = (
    Notice(
        "official_l1_winter",
        "Paseo del Altillo closed for roadworks",
        "A partir del 13 de abril de 2026, el Paseo del Altillo quedará cerrado al "
        "tráfico con motivo de las obras de mejora en el Paseo de la Caletilla. La "
        "duración estimada de los trabajos es de aproximadamente 10 meses. Durante "
        "este periodo, las líneas de autobús urbano modificarán temporalmente su "
        "recorrido, desviándose por la calle Guadix hasta la finalización de las obras.",
        affects=("ALM_1",),
        starts=dt.date(2026, 4, 13),
    ),
    Notice(
        "official_l2_winter",
        "Feria de San José: 2B follows the 2A itinerary",
        "Durante los días comprendidos entre el 16 y el 22 de marzo, las expediciones "
        "de la línea 2B operarán siguiendo el itinerario de la línea 2A, debido a las "
        "modificaciones ocasionadas por la celebración de la Feria de San José.",
        affects=("ALM_2B",),
        starts=dt.date(2027, 3, 16),
        ends=dt.date(2027, 3, 22),
    ),
    Notice(
        "official_l3b_summer",
        "Line 3B extended to Cabria",
        "Las expediciones de esta «Línea 3B Velilla» se extenderán hasta la nueva "
        "parada en la rotonda Avda. Pintor Domínguez de Haro, junto a la playa de "
        "Cabria, desde el 17 de julio hasta el 15 de septiembre. "
        "Ubicación: https://maps.app.goo.gl/NRgV2ptYRabLfbrj6",
        affects=("ALM_3B",),
        starts=dt.date(2026, 7, 17),
        ends=dt.date(2026, 9, 15),
    ),
    Notice(
        "official_l2_winter",
        "Marina del Este not served in winter",
        "*Esta parada no se realiza en el horario de invierno. (Footnote attached to "
        "MARINA DEL ESTE* on the line 2B route diagram.)",
        affects=("ALM_2B",),
    ),
)

#: The operator's own route diagrams, transcribed as printed. These use the
#: operator's stop names, which do not match OpenStreetMap's; they are kept for
#: cross-checking stop counts and order rather than fed into pattern
#: reconciliation. "R" suffixes mark the return direction — the operator itself
#: treats the two directions as different stops.
DIAGRAMS: dict[str, tuple[str, ...]] = {
    "ALM_1": (
        "PLAZA DE LA CARRERA", "PLAZA MADRID", "PASEO DEL ALTILLO", "PEÑÓN DEL SANTO",
        "HOTEL PLAYA", "HOTEL HELIOS", "MAR DEL SOL", "CHINASOL", "RINCÓN CHINA",
        "LOS RAMOS", "PLAYA COTOBRO", "LOS RAMOS R", "RINCÓN CHINA R", "CHINASOL R",
        "BARRIO MARINOS", "AVD. MEDITERRÁNEO", "IES ANTIGUA SEXI", "COSTA BANANA R",
        "AVD. COSTA DEL SOL 2 R", "ALBAICÍN DEL MAR R", "AVDA. COSTA DEL SOL 1 R",
        "PLAZA DE LA CARRERA R",
    ),
    "ALM_2A": (
        "PLAZA DE LA CARRERA", "AVDA. COSTA DEL SOL 1", "ALBAICÍN DEL MAR",
        "AVDA. COSTA DEL SOL 2", "COSTA BANANA", "MIRADOR COTOBRO", "LA HERRADURA",
        "MERCADO", "P. ANDRES SEGOVIA 1", "P. ANDRES SEGOVIA 2", "PEÑA PARDA",
        "P. ANDRES SEGOVIA 2 R", "P. ANDRES SEGOVIA 1 R", "MERCADO R",
        "ACERA DEL PILAR", "LA HERRADURA R", "MIRADOR COTOBRO R", "COSTA BANANA R",
        "AVDA. COSTA DEL SOL 2 R", "ALBAICÍN DEL MAR R", "AVDA. COSTA DEL SOL 1 R",
        "PLAZA DE LA CARRERA R",
    ),
    "ALM_2B": (
        "PLAZA DE LA CARRERA", "AVDA. COSTA DEL SOL 1", "ALBAICÍN DEL MAR",
        "AVDA. COSTA DEL SOL 2", "COSTA BANANA", "MIRADOR COTOBRO", "LA HERRADURA",
        "MERCADO", "P. ANDRES SEGOVIA 1", "P. ANDRES SEGOVIA 2", "PEÑA PARDA",
        "P. ANDRES SEGOVIA 2 R", "P. ANDRES SEGOVIA 1 R", "MERCADO R",
        "REST. BAMBÚ", "LA CALETA", "HOTEL FENICIOS", "PUNTA MONA",
        "HOTEL BEST ALCAZAR", "MARINA DEL ESTE*", "HOTEL BEST ALCAZAR R",
        "C/ EL MORRO", "FLOR DE HIERRO", "MIRADOR COTOBRO R", "COSTA BANANA R",
        "AVDA. COSTA DEL SOL 2 R", "ALBAICÍN DEL MAR R", "AVDA. COSTA DEL SOL 1 R",
        "PLAZA DE LA CARRERA R",
    ),
    "ALM_TORRECUEVAS": (
        "PLAZA DE LA CARRERA", "SAN SEBASTIAN 1", "SAN SEBASTIAN 2",
        "LADERAS DE CASTELAR", "CEMENTERIO", "PEÑUELAS", "VTA LUCIANO 1",
        "VTA LUCIANO 2", "TORRECUEVAS", "ARCOS TORRECUEVAS", "EUCALIPTO",
        "CAHICILLOS 1", "CAHICILLOS 2", "CAHICILLOS 1 R", "EUCALIPTO R",
        "ARCOS TORRECUEVAS R", "TORRECUEVAS R", "VTA LUCIANO 2 R", "VTA LUCIANO 1 R",
        "PEÑUELAS R", "CEMENTERIO R", "LADERAS DE CASTELAR R", "SAN SEBASTIAN 2 R",
        "SAN SEBASTIAN 1 R", "PLAZA DE LA CARRERA R",
    ),
    "ALM_3A": (
        "PLAZA DE LA CARRERA", "EST. AUTOBUSES", "AVD. JUAN CARLOS I", "PUERTA DEL MAR",
        "GONDOLAS", "P. REINA SOFIA", "AQUATROPIC", "ESPIGON", "P. TROPICAL 1",
        "P. TROPICAL 2", "VELILLA 1", "VELILLA 2", "VELILLA 3", "VELILLA 4",
        "TESORILLO 1", "POZUELO", "GALERA 1", "PLAYA CALIDA", "ESCUELAS TARAMAY",
        "HERCOFRUT", "ESCUELAS TARAMAY R", "TARAMAY R", "PORTICHUELO R", "LA PALOMA R",
        "AVD. FENICIA", "PLAZA DE LA CARRERA R",
    ),
    "ALM_3C": (
        "PLAZA DE LA CARRERA", "PORTICHUELO", "TARAMAY", "ESCUELAS TARAMAY",
        "HERCOFRUT", "ESCUELAS TARAMAY R", "TARAMAY R", "PORTICHUELO R", "LA PALOMA R",
        "AVD. FENICIA", "PLAZA DE LA CARRERA R",
    ),
    "ALM_3B": (
        "EST. AUTOBUSES", "AVD. JUAN CARLOS", "PUERTA DEL MAR", "GONDOLAS",
        "P. REINA SOFIA", "AQUATROPIC", "ESPIGON", "P. TROPICAL 1", "P. TROPICAL 2",
        "VELILLA 1", "VELILLA 2", "VELILLA 3", "VELILLA 4", "TESORILLO 1", "POZUELO",
        "GALERA 1", "PLAYA CALIDA", "ESCUELAS TARAMAY*", "HERCOFRUT*",
        "ESCUELAS TARAMAY R*", "TARAMAY R*", "PORTICHUELO R*", "POZUELO R**",
        "TESORILLO 1 R", "VELILLA 4 R", "VELILLA 3 R", "VELILLA 2 R", "VELILLA 1 R",
        "P. TROPICAL 2 R", "P. TROPICAL 1 R", "ESPIGON R", "AQUATROPIC R",
        "P. REINA SOFIA R", "GONDOLAS R", "PUERTA DEL MAR R", "AVD. JUAN CARLOS I R",
        "EST. AUTOBUSES R",
    ),
}


def fetch_pages(cache_dir: Path, *, force: bool = False) -> dict[str, FetchResult]:
    return {page.source_id: fetch(page.url, cache_dir, force=force) for page in PAGES}


def timetables_for(route_id: str) -> list[Timetable]:
    return [t for t in TIMETABLES if t.route_id == route_id]


def routes_covered() -> list[str]:
    seen: dict[str, None] = {}
    for timetable in TIMETABLES:
        seen.setdefault(timetable.route_id, None)
    return list(seen)
