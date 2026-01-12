"""Graph construction from road geometries with correct topology."""

from collections import defaultdict
from typing import Optional

import geopandas as gpd
import networkx as nx
import numpy as np
from pyproj import Geod
from shapely.geometry import LineString, MultiLineString, Point


class GraphBuilder:
    """Build NetworkX graph from road GeoDataFrame with correct topology."""

    # Coordinate precision for snapping (6 decimal places ~ 0.1m precision)
    COORD_PRECISION = 6

    # Snapping tolerance in meters for connecting nearby endpoints
    SNAP_TOLERANCE_METERS = 1.0

    def __init__(
        self,
        coord_precision: int = 6,
        snap_tolerance_meters: float = 1.0,
    ):
        """
        Initialize the graph builder.

        Args:
            coord_precision: Decimal places for coordinate rounding (default 6).
            snap_tolerance_meters: Distance in meters to snap nearby endpoints.
        """
        self.coord_precision = coord_precision
        self.snap_tolerance_meters = snap_tolerance_meters
        self._geod = Geod(ellps="WGS84")

    def _round_coord(self, x: float, y: float) -> tuple[float, float]:
        """Round coordinates to the configured precision."""
        return (round(x, self.coord_precision), round(y, self.coord_precision))

    def _geodesic_distance(self, lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        """
        Calculate geodesic distance between two points in meters.

        Args:
            lon1, lat1: First point (longitude, latitude in degrees).
            lon2, lat2: Second point (longitude, latitude in degrees).

        Returns:
            Distance in meters.
        """
        _, _, distance = self._geod.inv(lon1, lat1, lon2, lat2)
        return abs(distance)

    def _line_length_meters(self, coords: list[tuple[float, float]]) -> float:
        """
        Calculate the total length of a line segment in meters.

        Args:
            coords: List of (x, y) coordinate tuples (lon, lat in degrees).

        Returns:
            Total length in meters.
        """
        total = 0.0
        for i in range(len(coords) - 1):
            total += self._geodesic_distance(
                coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]
            )
        return total

    def _extract_linestrings(self, geometry) -> list[LineString]:
        """Extract all LineStrings from a geometry (handles MultiLineString)."""
        if geometry is None or geometry.is_empty:
            return []
        if isinstance(geometry, LineString):
            return [geometry]
        if isinstance(geometry, MultiLineString):
            return list(geometry.geoms)
        return []

    def _snap_to_existing(
        self,
        coord: tuple[float, float],
        existing_nodes: dict[tuple[float, float], int],
        tolerance_degrees: float,
    ) -> Optional[tuple[float, float]]:
        """
        Find if there's an existing node within snap tolerance.

        Args:
            coord: The coordinate to check.
            existing_nodes: Dict mapping coordinates to node IDs.
            tolerance_degrees: Approximate tolerance in degrees.

        Returns:
            The existing coordinate if within tolerance, None otherwise.
        """
        for existing_coord in existing_nodes:
            dx = abs(coord[0] - existing_coord[0])
            dy = abs(coord[1] - existing_coord[1])
            # Quick check using Chebyshev distance in degrees
            if dx <= tolerance_degrees and dy <= tolerance_degrees:
                # Verify with actual geodesic distance
                dist = self._geodesic_distance(
                    coord[0], coord[1], existing_coord[0], existing_coord[1]
                )
                if dist <= self.snap_tolerance_meters:
                    return existing_coord
        return None

    def build_graph(self, roads: gpd.GeoDataFrame) -> nx.Graph:
        """
        Convert road GeoDataFrame to NetworkX graph.

        Algorithm:
        1. Extract all endpoints from LineStrings
        2. Round coordinates and snap nearby endpoints
        3. Collect all vertices to identify intersections
        4. Create nodes for endpoints and intersection points
        5. Create edges between consecutive nodes along each LineString
        6. Calculate edge weights as geodesic distance

        Args:
            roads: GeoDataFrame with LineString geometries.

        Returns:
            NetworkX Graph with nodes having x, y attributes and
            edges having weight (meters) and geometry attributes.
        """
        if roads.empty:
            return nx.Graph()

        # Ensure we're working with WGS84 for geodesic calculations
        if roads.crs is not None and roads.crs.to_epsg() != 4326:
            roads = roads.to_crs("EPSG:4326")

        # Approximate tolerance in degrees (1 meter ~ 0.00001 degrees at mid-latitudes)
        tolerance_degrees = self.snap_tolerance_meters * 0.00001

        # Phase 1: Collect all vertices and count occurrences
        vertex_count = defaultdict(int)
        all_linestrings = []

        for geom in roads.geometry:
            linestrings = self._extract_linestrings(geom)
            for ls in linestrings:
                if ls is None or ls.is_empty or len(ls.coords) < 2:
                    continue
                all_linestrings.append(ls)
                coords = list(ls.coords)

                # Mark endpoints (always nodes)
                start = self._round_coord(coords[0][0], coords[0][1])
                end = self._round_coord(coords[-1][0], coords[-1][1])
                vertex_count[start] += 1
                vertex_count[end] += 1

                # Mark intermediate vertices
                for coord in coords[1:-1]:
                    rounded = self._round_coord(coord[0], coord[1])
                    vertex_count[rounded] += 1

        # Phase 2: Identify nodes (endpoints + intersection points)
        # A vertex is an intersection if it appears in multiple LineStrings
        # OR if it's an endpoint of any LineString
        endpoint_coords = set()
        for ls in all_linestrings:
            coords = list(ls.coords)
            endpoint_coords.add(self._round_coord(coords[0][0], coords[0][1]))
            endpoint_coords.add(self._round_coord(coords[-1][0], coords[-1][1]))

        # Nodes are: endpoints OR vertices that appear multiple times (intersections)
        node_coords = set()
        for coord, count in vertex_count.items():
            if coord in endpoint_coords or count > 1:
                node_coords.add(coord)

        # Phase 3: Apply snapping to merge nearby nodes
        coord_to_node = {}
        node_id = 0

        # Sort for deterministic ordering
        sorted_coords = sorted(node_coords)

        for coord in sorted_coords:
            snapped = self._snap_to_existing(coord, coord_to_node, tolerance_degrees)
            if snapped is not None:
                # Map this coord to the existing node's coord
                coord_to_node[coord] = coord_to_node[snapped]
            else:
                coord_to_node[coord] = node_id
                node_id += 1

        # Phase 4: Build the graph
        G = nx.Graph()

        # Add all unique nodes with coordinates
        node_coords_by_id = {}
        for coord, nid in coord_to_node.items():
            if nid not in node_coords_by_id:
                node_coords_by_id[nid] = coord

        for nid, coord in node_coords_by_id.items():
            G.add_node(nid, x=coord[0], y=coord[1])

        # Phase 5: Create edges from LineStrings
        for ls in all_linestrings:
            coords = list(ls.coords)
            if len(coords) < 2:
                continue

            # Find nodes along this LineString and create edges
            current_node_coord = None
            segment_coords = []

            for i, coord in enumerate(coords):
                rounded = self._round_coord(coord[0], coord[1])
                segment_coords.append((coord[0], coord[1]))

                # Check if this is a node point
                if rounded in coord_to_node:
                    if current_node_coord is not None and len(segment_coords) >= 2:
                        # Create edge from current_node to this node
                        from_node = coord_to_node[current_node_coord]
                        to_node = coord_to_node[rounded]

                        if from_node != to_node:
                            # Calculate weight as geodesic distance
                            weight = self._line_length_meters(segment_coords)

                            # Create edge geometry
                            edge_geom = LineString(segment_coords)

                            # Add or update edge (keep shorter if duplicate)
                            if G.has_edge(from_node, to_node):
                                existing_weight = G[from_node][to_node]["weight"]
                                if weight < existing_weight:
                                    G[from_node][to_node]["weight"] = weight
                                    G[from_node][to_node]["geometry"] = edge_geom
                            else:
                                G.add_edge(
                                    from_node,
                                    to_node,
                                    weight=weight,
                                    geometry=edge_geom,
                                )

                    # Start new segment from this node
                    current_node_coord = rounded
                    segment_coords = [(coord[0], coord[1])]

        return G

    def validate_graph(self, graph: nx.Graph) -> dict:
        """
        Validate the constructed graph and return a report.

        Args:
            graph: The NetworkX graph to validate.

        Returns:
            Validation report dict with stats and issues.
        """
        issues = []

        # Basic counts
        node_count = graph.number_of_nodes()
        edge_count = graph.number_of_edges()

        # Check if empty
        if node_count == 0:
            issues.append("Graph is empty (no nodes)")
            return {
                "node_count": 0,
                "edge_count": 0,
                "connected_components": 0,
                "largest_component_size": 0,
                "isolated_nodes": 0,
                "valid": False,
                "issues": issues,
            }

        # Connected components
        components = list(nx.connected_components(graph))
        num_components = len(components)
        largest_component_size = max(len(c) for c in components) if components else 0

        # Isolated nodes (degree 0)
        isolated_nodes = sum(1 for n in graph.nodes() if graph.degree(n) == 0)
        if isolated_nodes > 0:
            issues.append(f"Graph has {isolated_nodes} isolated nodes (degree 0)")

        # Check edge weights
        invalid_weights = 0
        for u, v, data in graph.edges(data=True):
            weight = data.get("weight", None)
            if weight is None or weight <= 0:
                invalid_weights += 1

        if invalid_weights > 0:
            issues.append(f"Graph has {invalid_weights} edges with invalid weights")

        # Check node attributes
        nodes_missing_coords = 0
        for node in graph.nodes():
            if "x" not in graph.nodes[node] or "y" not in graph.nodes[node]:
                nodes_missing_coords += 1

        if nodes_missing_coords > 0:
            issues.append(f"{nodes_missing_coords} nodes missing coordinate attributes")

        # Determine validity
        valid = len(issues) == 0 or (
            len(issues) == 1 and isolated_nodes > 0 and isolated_nodes < node_count * 0.01
        )

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "connected_components": num_components,
            "largest_component_size": largest_component_size,
            "isolated_nodes": isolated_nodes,
            "valid": valid,
            "issues": issues,
        }

    def build_and_validate(
        self, roads: gpd.GeoDataFrame
    ) -> tuple[nx.Graph, dict]:
        """
        Build graph and validate it in one call.

        Args:
            roads: GeoDataFrame with LineString geometries.

        Returns:
            Tuple of (graph, validation_report).
        """
        graph = self.build_graph(roads)
        report = self.validate_graph(graph)
        return graph, report
