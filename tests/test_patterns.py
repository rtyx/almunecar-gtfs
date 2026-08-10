"""Route pattern and geometry invariants (plan tasks 5, 6 and 10)."""

from __future__ import annotations

import pytest

from almunecar_gtfs import qa
from almunecar_gtfs.models import (
    Pattern,
    PatternStop,
    PublicationStatus,
    Season,
    Shape,
    TimingMethod,
)
from almunecar_gtfs.provenance import Confidence, EvidenceStore
from almunecar_gtfs.reconcile.patterns import reconcile_patterns

from .conftest import FIXTURE_SOURCES, observation


def pattern_stop(stop_id: str, offset: int | None, method=TimingMethod.PUBLISHED) -> PatternStop:
    return PatternStop(stop_id=stop_id, offset_seconds=offset, timing_method=method)


def test_a_pattern_needs_at_least_two_stops():
    with pytest.raises(ValueError):
        Pattern(
            pattern_id="P",
            route_id="R",
            direction_id=0,
            season=Season.SUMMER,
            headsign="X",
            stops=[pattern_stop("ALM_0001", 0)],
        )


def test_offsets_may_not_move_backwards():
    with pytest.raises(ValueError, match="backwards"):
        Pattern(
            pattern_id="P",
            route_id="R",
            direction_id=0,
            season=Season.SUMMER,
            headsign="X",
            stops=[pattern_stop("ALM_0001", 0), pattern_stop("ALM_0002", -60)],
        )


def test_the_origin_offset_must_be_zero():
    with pytest.raises(ValueError, match="first stop offset"):
        Pattern(
            pattern_id="P",
            route_id="R",
            direction_id=0,
            season=Season.SUMMER,
            headsign="X",
            stops=[pattern_stop("ALM_0001", 120), pattern_stop("ALM_0002", 240)],
        )


def test_a_stop_may_not_repeat_consecutively():
    with pytest.raises(ValueError, match="repeats consecutively"):
        Pattern(
            pattern_id="P",
            route_id="R",
            direction_id=0,
            season=Season.SUMMER,
            headsign="X",
            stops=[pattern_stop("ALM_0001", 0), pattern_stop("ALM_0001", 60)],
        )


def test_a_circular_route_may_revisit_a_stop_later():
    """Line 1 is a circular; returning to an earlier stop is legitimate."""
    pattern = Pattern(
        pattern_id="P",
        route_id="R",
        direction_id=0,
        season=Season.SUMMER,
        headsign="Circular",
        stops=[
            pattern_stop("ALM_0001", 0),
            pattern_stop("ALM_0002", 300),
            pattern_stop("ALM_0001", 900),
        ],
    )
    assert pattern.stop_ids == ["ALM_0001", "ALM_0002", "ALM_0001"]


def test_a_pattern_with_unknown_offsets_is_not_publishable():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("pattern:P", "route_id", "R"),
            observation("pattern:P", "headsign", "X"),
            observation("pattern:P", "stop_sequence", "ALM_0001;ALM_0002;ALM_0003"),
            observation("pattern:P", "offsets", "0;?;600"),
        ],
    )
    patterns, problems = reconcile_patterns(store)
    assert problems == []
    assert patterns[0].status is PublicationStatus.NOT_PUBLISHABLE
    assert not patterns[0].has_complete_timings


def test_missing_offsets_do_not_become_invented_times():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("pattern:P", "route_id", "R"),
            observation("pattern:P", "headsign", "X"),
            observation("pattern:P", "stop_sequence", "ALM_0001;ALM_0002;ALM_0003"),
        ],
    )
    patterns, _ = reconcile_patterns(store)
    assert [stop.offset_seconds for stop in patterns[0].stops] == [0, None, None]
    assert patterns[0].status is PublicationStatus.NOT_PUBLISHABLE


def test_derived_timings_are_marked_as_estimates(network):
    pattern = network.patterns_by_id["ALM_9_OUT"]
    assert [stop.is_timepoint for stop in pattern.stops] == [True, False, False, True]
    assert pattern.timing_model is not None
    assert pattern.timing_model.method is TimingMethod.OBSERVED_MEDIAN
    assert pattern.timing_model.sample_size == 7


def test_a_median_timing_model_without_a_sample_size_is_an_error(network):
    pattern = network.patterns_by_id["ALM_9_OUT"]
    broken = pattern.model_copy(
        update={"timing_model": pattern.timing_model.model_copy(update={"sample_size": None})}
    )
    findings = qa.check_patterns(network.model_copy(update={"patterns": [broken]}))
    assert any(f.code == "pattern.median_without_samples" for f in findings)


def test_conditional_behaviour_is_modelled_explicitly_not_assumed():
    """Line 2B's Puerto Marina behaviour has to be stated, not inferred."""
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("pattern:P_NO_PORT", "route_id", "ALM_2B"),
            observation("pattern:P_NO_PORT", "headsign", "La Herradura"),
            observation("pattern:P_NO_PORT", "stop_sequence", "ALM_0001;ALM_0002"),
            observation("pattern:P_NO_PORT", "variant_code", "NOPORT"),
            observation(
                "pattern:P_NO_PORT",
                "conditional",
                "Runs when Puerto Marina del Este is not served",
            ),
        ],
    )
    patterns, problems = reconcile_patterns(store)
    assert problems == []
    assert patterns[0].variant_code == "NOPORT"
    assert "Puerto Marina" in patterns[0].conditional


def test_shape_geometry_is_loaded_with_its_provenance(network):
    shape = network.shapes_by_id["ALM_9_OUT"]
    assert shape.source_id == "fixture_operator"
    assert len(shape.points) > 2


def test_the_shape_passes_close_to_every_stop_it_serves(network):
    findings = qa.check_geometry(network)
    assert [f for f in findings if f.severity is qa.Severity.ERROR] == []


def test_a_straight_line_between_distant_stops_is_rejected():
    """Naive stop-to-stop geometry must not reach the production feed."""
    naive = Shape(
        shape_id="NAIVE",
        points=[(36.7350, -3.6890), (36.7290, -3.7350)],
        source_id="fixture_operator",
        confidence=Confidence.LOW,
    )
    from almunecar_gtfs.models import Agency, FeedInfo, Network

    network = Network(
        agency=Agency(agency_id="ALM", agency_name="x", agency_url="https://example.invalid"),
        feed_info=FeedInfo(
            feed_publisher_name="x", feed_publisher_url="https://example.invalid", feed_version="1"
        ),
        shapes=[naive],
    )
    findings = qa.check_geometry(network)
    assert any(f.code == "shape.implausible_jump" for f in findings)


def test_a_pattern_referencing_an_unknown_stop_is_an_error(network):
    pattern = network.patterns_by_id["ALM_9_OUT"]
    broken = pattern.model_copy(
        update={"stops": [*pattern.stops[:-1], pattern_stop("ALM_8888", 1200)]}
    )
    findings = qa.check_patterns(network.model_copy(update={"patterns": [broken]}))
    assert any(f.code == "pattern.unknown_stop" for f in findings)


def test_a_trip_may_not_ship_with_an_estimated_first_or_last_call(network):
    """GTFS allows an estimated middle; it does not allow guessed ends."""
    pattern = network.patterns_by_id["ALM_9_OUT"]
    assert pattern.has_anchored_endpoints
    assert pattern.is_publishable

    guessed_end = pattern.model_copy(
        update={
            "stops": [
                *pattern.stops[:-1],
                pattern.stops[-1].model_copy(
                    update={"timing_method": TimingMethod.INTERPOLATED}
                ),
            ]
        }
    )
    assert not guessed_end.has_anchored_endpoints
    assert not guessed_end.is_publishable

    findings = qa.check_patterns(network.model_copy(update={"patterns": [guessed_end]}))
    assert any(f.code == "pattern.unanchored_endpoints" for f in findings)


def test_an_estimated_middle_is_fine_when_the_ends_are_published(network):
    pattern = network.patterns_by_id["ALM_9_OUT"]
    # The fixture already has observed_median middles and published ends.
    assert [s.timing_method for s in pattern.stops[1:-1]] == [
        TimingMethod.OBSERVED_MEDIAN,
        TimingMethod.OBSERVED_MEDIAN,
    ]
    assert pattern.is_publishable
    assert not [
        f for f in qa.check_patterns(network) if f.code == "pattern.unanchored_endpoints"
    ]


def test_a_pattern_with_guessed_ends_never_reaches_the_feed(network):
    from almunecar_gtfs.gtfs import build as build_mod

    pattern = network.patterns_by_id["ALM_9_OUT"]
    guessed = pattern.model_copy(
        update={
            "stops": [
                pattern.stops[0].model_copy(update={"timing_method": TimingMethod.INTERPOLATED}),
                *pattern.stops[1:],
            ]
        }
    )
    with pytest.raises(build_mod.BuildError, match="no publishable trips"):
        build_mod.build_feed(network.model_copy(update={"patterns": [guessed]}))


def test_a_scrambled_stop_sequence_is_caught_even_though_every_stop_is_on_the_route(network):
    """Proximity alone cannot see this: every stop is still beside the line.

    One out-of-order jump is indistinguishable from a loop closing, so the check
    tolerates it. Two is a scrambled sequence, which is what OSM's Torrecuevas
    relation actually contained.
    """
    pattern = network.patterns_by_id["ALM_9_OUT"]
    order = [0, 2, 1, 3, 2]
    scrambled = pattern.model_copy(
        update={
            "stops": [
                pattern.stops[position].model_copy(update={"offset_seconds": seconds})
                for position, seconds in zip(order, [0, 240, 480, 900, 1200], strict=True)
            ]
        }
    )
    candidate = network.model_copy(update={"patterns": [scrambled]})

    # Every stop is still within tolerance of the shape...
    assert not [f for f in qa.check_geometry(candidate) if f.severity is qa.Severity.ERROR]
    # ...but the order disagrees with the geometry.
    findings = qa.check_stop_order(candidate)
    assert any(f.code == "pattern.stop_order_disagrees_with_shape" for f in findings)


def test_a_correctly_ordered_sequence_passes_the_order_check(network):
    assert qa.check_stop_order(network) == []


def test_a_loop_returning_to_its_origin_is_not_flagged(network):
    """One wrap is legitimate: these lines all end where they began."""
    pattern = network.patterns_by_id["ALM_9_OUT"]
    looped = pattern.model_copy(
        update={
            "stops": [
                *pattern.stops,
                pattern.stops[0].model_copy(update={"offset_seconds": 1800}),
            ]
        }
    )
    findings = qa.check_stop_order(network.model_copy(update={"patterns": [looped]}))
    assert findings == []
