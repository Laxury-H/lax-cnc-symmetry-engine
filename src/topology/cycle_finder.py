"""
Closed loop and cycle extraction from TopologyGraph.
Extracts ordered polygon loops, computes area, centroid, winding order, and nesting.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Set, Optional
import networkx as nx
import numpy as np

from src.core.primitives import Point2D, LineSegment2D, Arc2D, BoundingBox2D
from src.topology.graph import TopologyGraph, TopologyNode, TopologyEdge


@dataclass
class ClosedLoop:
    """A closed polygon loop / cycle extracted from CAD topology."""
    loop_id: int
    node_ids: List[int]
    points: List[Point2D]
    edges: List[TopologyEdge] = field(default_factory=list)

    @property
    def num_vertices(self) -> int:
        return len(self.points)

    @property
    def signed_area(self) -> float:
        """Signed area using Shoelace formula. Positive = CCW, Negative = CW."""
        n = len(self.points)
        if n < 3:
            return 0.0
        x = np.array([p.x for p in self.points] + [self.points[0].x], dtype=np.float64)
        y = np.array([p.y for p in self.points] + [self.points[0].y], dtype=np.float64)
        return float(0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))

    @property
    def area(self) -> float:
        return abs(self.signed_area)

    @property
    def is_counter_clockwise(self) -> bool:
        return self.signed_area > 0

    @property
    def centroid(self) -> Point2D:
        """Polygon centroid calculation."""
        n = len(self.points)
        if n == 0:
            return Point2D(0.0, 0.0)
        if n < 3:
            return Point2D(
                sum(p.x for p in self.points) / n,
                sum(p.y for p in self.points) / n
            )
        # Standard polygon centroid
        x = np.array([p.x for p in self.points] + [self.points[0].x], dtype=np.float64)
        y = np.array([p.y for p in self.points] + [self.points[0].y], dtype=np.float64)
        cross_term = x[:-1] * y[1:] - x[1:] * y[:-1]
        area = 0.5 * np.sum(cross_term)
        if abs(area) < 1e-9:
            return Point2D(float(np.mean(x[:-1])), float(np.mean(y[:-1])))
        cx = float(np.sum((x[:-1] + x[1:]) * cross_term) / (6.0 * area))
        cy = float(np.sum((y[:-1] + y[1:]) * cross_term) / (6.0 * area))
        return Point2D(cx, cy)

    @property
    def perimeter(self) -> float:
        p = 0.0
        n = len(self.points)
        for i in range(n):
            p += self.points[i].distance_to(self.points[(i + 1) % n])
        return p

    @property
    def bbox(self) -> BoundingBox2D:
        return BoundingBox2D.from_points(self.points)


class CycleFinder:
    """Extracts all simple closed loops from TopologyGraph."""

    def __init__(self, graph: TopologyGraph):
        self.graph = graph

    def extract_loops(self) -> List[ClosedLoop]:
        """Extract all minimal closed cycles from the graph."""
        nx_g = self.graph.nx_graph
        if nx_g.number_of_nodes() == 0:
            return []

        # Find cycle basis of each connected component
        cycles = nx.cycle_basis(nx_g)
        loops: List[ClosedLoop] = []

        for loop_id, cycle_nodes in enumerate(cycles):
            # Order the cycle nodes along a contiguous path
            ordered_nodes = self._order_cycle_nodes(cycle_nodes, nx_g)
            ordered_points = [self.graph.nodes[nid].point for nid in ordered_nodes]

            # Find matching edges connecting adjacent nodes
            cycle_edges = []
            for i in range(len(ordered_nodes)):
                u = ordered_nodes[i]
                v = ordered_nodes[(i + 1) % len(ordered_nodes)]
                edge_data = nx_g.get_edge_data(u, v)
                if edge_data and "edge_id" in edge_data:
                    cycle_edges.append(self.graph.edges[edge_data["edge_id"]])

            loop = ClosedLoop(
                loop_id=loop_id,
                node_ids=ordered_nodes,
                points=ordered_points,
                edges=cycle_edges
            )
            loops.append(loop)

        # Sort loops by area descending (largest first)
        loops.sort(key=lambda l: l.area, reverse=True)
        return loops

    def _order_cycle_nodes(self, cycle_nodes: List[int], nx_g: nx.Graph) -> List[int]:
        """Ensure cycle nodes are in circular traversal order."""
        if len(cycle_nodes) <= 2:
            return cycle_nodes

        subgraph = nx_g.subgraph(cycle_nodes)
        # Find an Eulerian or Hamiltonian path in the cycle subgraph
        start_node = cycle_nodes[0]
        visited = [start_node]
        current = start_node
        remaining = set(cycle_nodes) - {start_node}

        while remaining:
            neighbors = [nb for nb in subgraph.neighbors(current) if nb in remaining]
            if not neighbors:
                # Disconnect fallback
                visited.extend(list(remaining))
                break
            nxt = neighbors[0]
            visited.append(nxt)
            remaining.remove(nxt)
            current = nxt

        return visited
