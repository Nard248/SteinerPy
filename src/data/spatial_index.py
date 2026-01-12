"""Spatial index for efficient node queries on road network graphs."""

from typing import Optional

import networkx as nx
from rtree import index


class SpatialIndex:
    """R-tree spatial index for efficient nearest-neighbor and range queries on graph nodes."""

    def __init__(self, graph: nx.Graph):
        """
        Build an R-tree index from graph node coordinates.

        Args:
            graph: NetworkX graph with nodes having 'x' and 'y' attributes.
        """
        self._graph = graph
        self._node_coords = {}
        self._idx = index.Index()

        # Build the index
        for node in graph.nodes():
            x = graph.nodes[node].get("x")
            y = graph.nodes[node].get("y")
            if x is not None and y is not None:
                self._node_coords[node] = (x, y)
                # R-tree uses (minx, miny, maxx, maxy) bounding box
                # For points, min = max
                self._idx.insert(node, (x, y, x, y))

    @property
    def node_count(self) -> int:
        """Return the number of indexed nodes."""
        return len(self._node_coords)

    def nearest_node(
        self, x: float, y: float, k: int = 1
    ) -> list[int]:
        """
        Find the k nearest nodes to a given point.

        Args:
            x: X coordinate (longitude).
            y: Y coordinate (latitude).
            k: Number of nearest nodes to return (default 1).

        Returns:
            List of node IDs sorted by distance (closest first).
        """
        # R-tree nearest returns generator of node IDs
        nearest = list(self._idx.nearest((x, y, x, y), k))
        return nearest

    def nodes_in_bbox(
        self, bbox: tuple[float, float, float, float]
    ) -> list[int]:
        """
        Find all nodes within a bounding box.

        Args:
            bbox: (minx, miny, maxx, maxy) bounding box coordinates.

        Returns:
            List of node IDs within the bounding box.
        """
        minx, miny, maxx, maxy = bbox
        return list(self._idx.intersection((minx, miny, maxx, maxy)))

    def get_node_coords(self, node_id: int) -> Optional[tuple[float, float]]:
        """
        Get the coordinates of a node by ID.

        Args:
            node_id: The node ID.

        Returns:
            (x, y) tuple or None if node not found.
        """
        return self._node_coords.get(node_id)

    def nodes_in_radius(
        self, x: float, y: float, radius_degrees: float
    ) -> list[int]:
        """
        Find all nodes within a radius of a point.

        Note: This uses a bounding box approximation for efficiency,
        then filters by actual Euclidean distance in coordinate space.
        For accurate geodesic radius queries, results should be
        filtered further using actual geodesic distances.

        Args:
            x: X coordinate (longitude).
            y: Y coordinate (latitude).
            radius_degrees: Radius in degrees.

        Returns:
            List of node IDs within the radius.
        """
        # Get candidates from bounding box
        bbox = (x - radius_degrees, y - radius_degrees, x + radius_degrees, y + radius_degrees)
        candidates = self.nodes_in_bbox(bbox)

        # Filter by actual distance
        result = []
        radius_sq = radius_degrees * radius_degrees
        for node in candidates:
            nx, ny = self._node_coords[node]
            dist_sq = (nx - x) ** 2 + (ny - y) ** 2
            if dist_sq <= radius_sq:
                result.append(node)

        return result
