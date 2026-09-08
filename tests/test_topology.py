"""Unit tests for topological graph and cycle finding."""

import pytest
from src.core.primitives import Point2D, LineSegment2D
from src.io.dxf_io import CADModel2D
from src.topology.graph import TopologyGraph
from src.topology.cycle_finder import CycleFinder


def test_topology_closed_rectangle():
    # Construct a 100 x 50 rectangle
    p1 = Point2D(0.0, 0.0)
    p2 = Point2D(100.0, 0.0)
    p3 = Point2D(100.0, 50.0)
    p4 = Point2D(0.0, 50.0)

    lines = [
        LineSegment2D(p1, p2),
        LineSegment2D(p2, p3),
        LineSegment2D(p3, p4),
        LineSegment2D(p4, p1),
    ]
    model = CADModel2D(lines=lines)
    graph = TopologyGraph.from_cad_model(model, endpoint_tolerance=0.05)

    assert graph.num_nodes == 4
    assert graph.num_edges == 4
    assert graph.is_watertight
    assert len(graph.open_endpoints) == 0

    finder = CycleFinder(graph)
    loops = finder.extract_loops()
    assert len(loops) == 1

    loop = loops[0]
    assert loop.num_vertices == 4
    assert loop.area == pytest.approx(5000.0)
    assert loop.centroid.x == pytest.approx(50.0)
    assert loop.centroid.y == pytest.approx(25.0)
    assert loop.perimeter == pytest.approx(300.0)


def test_topology_with_micro_gap():
    # Endpoints differ by 0.02 mm (< 0.10 mm tolerance)
    p1 = Point2D(0.0, 0.0)
    p2 = Point2D(50.0, 0.0)
    p2_gap = Point2D(50.02, 0.01)
    p3 = Point2D(50.0, 50.0)
    p4 = Point2D(0.0, 50.0)

    lines = [
        LineSegment2D(p1, p2),
        LineSegment2D(p2_gap, p3),
        LineSegment2D(p3, p4),
        LineSegment2D(p4, p1),
    ]
    model = CADModel2D(lines=lines)
    graph = TopologyGraph.from_cad_model(model, endpoint_tolerance=0.05)

    # Should successfully cluster p2 and p2_gap into a single node
    assert graph.num_nodes == 4
    assert graph.is_watertight
