"""
Topological Graph for CAD entities.
Provides vertex clustering with tolerance, degree analysis, and adjacency graph.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Set, Optional, Any
import math
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from src.core.primitives import Point2D, LineSegment2D, Arc2D, BoundingBox2D
from src.io.dxf_io import CADModel2D


@dataclass
class TopologyNode:
    """Graph node representing a clustered vertex position."""
    node_id: int
    point: Point2D
    original_points: List[Point2D] = field(default_factory=list)

    @property
    def degree(self) -> int:
        return len(self.connected_edge_ids)

    connected_edge_ids: Set[int] = field(default_factory=set)


@dataclass
class TopologyEdge:
    """Graph edge representing a geometric entity connecting two nodes."""
    edge_id: int
    u: int  # Start node ID
    v: int  # End node ID
    geometry: LineSegment2D | Arc2D
    length: float
    layer: str = "0"


class TopologyGraph:
    """
    Planar graph representation of CAD entities with tolerance-based vertex clustering.
    """

    def __init__(self, endpoint_tolerance: float = 0.10):
        self.tolerance = endpoint_tolerance
        self.nodes: Dict[int, TopologyNode] = {}
        self.edges: Dict[int, TopologyEdge] = {}
        self.nx_graph = nx.Graph()

    @classmethod
    def from_cad_model(cls, model: CADModel2D, endpoint_tolerance: float = 0.10) -> TopologyGraph:
        """Construct topology graph from CAD model entities."""
        tg = cls(endpoint_tolerance=endpoint_tolerance)

        # Collect all endpoints from lines and arcs
        raw_endpoints: List[Point2D] = []
        entity_endpoint_pairs: List[Tuple[Point2D, Point2D, LineSegment2D | Arc2D, str]] = []

        for line in model.lines:
            raw_endpoints.append(line.start)
            raw_endpoints.append(line.end)
            entity_endpoint_pairs.append((line.start, line.end, line, line.layer))

        for arc in model.arcs:
            p_start = arc.start_point
            p_end = arc.end_point
            raw_endpoints.append(p_start)
            raw_endpoints.append(p_end)
            entity_endpoint_pairs.append((p_start, p_end, arc, arc.layer))

        if not raw_endpoints:
            return tg

        # Cluster endpoints within tolerance using KDTree
        coords = np.array([[p.x, p.y] for p in raw_endpoints], dtype=np.float64)
        tree = cKDTree(coords)

        # Disjoint set / union-find to cluster points within tolerance
        n_pts = len(raw_endpoints)
        parent = list(range(n_pts))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        pairs = tree.query_pairs(r=endpoint_tolerance)
        for i, j in pairs:
            union(i, j)

        # Group indices by cluster root
        cluster_groups: Dict[int, List[int]] = {}
        for i in range(n_pts):
            r = find(i)
            cluster_groups.setdefault(r, []).append(i)

        # Create TopologyNode for each cluster with averaged position
        pt_idx_to_node_id: Dict[int, int] = {}
        for node_id, (root, member_indices) in enumerate(cluster_groups.items()):
            pts = [raw_endpoints[idx] for idx in member_indices]
            avg_x = sum(p.x for p in pts) / len(pts)
            avg_y = sum(p.y for p in pts) / len(pts)
            node_pt = Point2D(avg_x, avg_y)
            tg.nodes[node_id] = TopologyNode(
                node_id=node_id,
                point=node_pt,
                original_points=pts
            )
            for idx in member_indices:
                pt_idx_to_node_id[idx] = node_id

        # Now add edges
        edge_id = 0
        raw_pt_cursor = 0
        for p_start, p_end, geom, layer in entity_endpoint_pairs:
            u = pt_idx_to_node_id[raw_pt_cursor]
            v = pt_idx_to_node_id[raw_pt_cursor + 1]
            raw_pt_cursor += 2

            length = geom.length
            top_edge = TopologyEdge(
                edge_id=edge_id,
                u=u,
                v=v,
                geometry=geom,
                length=length,
                layer=layer
            )
            tg.edges[edge_id] = top_edge
            tg.nodes[u].connected_edge_ids.add(edge_id)
            tg.nodes[v].connected_edge_ids.add(edge_id)

            tg.nx_graph.add_edge(u, v, edge_id=edge_id, weight=length)
            edge_id += 1

        return tg

    @property
    def num_nodes(self) -> int:
        return len(self.nodes)

    @property
    def num_edges(self) -> int:
        return len(self.edges)

    @property
    def open_endpoints(self) -> List[TopologyNode]:
        """Nodes with degree 1 (open dangling ends)."""
        return [n for n in self.nodes.values() if n.degree == 1]

    @property
    def junction_nodes(self) -> List[TopologyNode]:
        """Nodes with degree >= 3 (branching junctions)."""
        return [n for n in self.nodes.values() if n.degree >= 3]

    @property
    def is_watertight(self) -> bool:
        """True if all nodes have even degree (Eulerian / watertight closed paths)."""
        if not self.nodes:
            return True
        return all(n.degree % 2 == 0 for n in self.nodes.values())
