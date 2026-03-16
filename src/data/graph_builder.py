"""
Graph construction from road geometries with correct topology.

=== GRAPH CONSTRUCTION PROCESS ===

The GraphBuilder converts road network geometries (LineStrings) into a NetworkX
graph suitable for Steiner tree algorithms.

Input:  GeoDataFrame with LineString/MultiLineString geometries
Output: NetworkX Graph with:
        - Nodes: road intersections and endpoints
        - Edges: road segments with distance weights (meters)

=== CONSTRUCTION PHASES ===

Phase 1: Vertex Collection
    - Extract all coordinates from all LineStrings
    - Round coordinates to configured precision (default 6 decimals ~ 0.1m)
    - Count how many times each vertex appears

Phase 2: Node Identification
    - Endpoints of LineStrings → always become nodes
    - Interior vertices appearing in multiple LineStrings → intersection nodes
    - This ensures the graph captures road topology correctly

Phase 3: Coordinate Snapping
    - Nearby nodes within snap_tolerance_meters are merged
    - This handles slight coordinate mismatches in the source data
    - Uses geodesic distance for accuracy

Phase 4: Graph Building
    - Create nodes with (x, y) coordinates
    - Create edges between consecutive nodes along each LineString

Phase 5: Weight Calculation
    - Edge weights are geodesic distances (WGS84 ellipsoid)
    - More accurate than Euclidean distance, especially over longer segments

=== COORDINATE SYSTEMS ===

The builder expects WGS84 (EPSG:4326) coordinates and will reproject if needed.
Edge weights are always in METERS regardless of input CRS.

=== DEVELOPER NOTES ===

- Node IDs are integers starting from 0
- Node attributes: 'x' (longitude), 'y' (latitude)
- Edge attributes: 'weight' (meters), 'geometry' (LineString)
- The graph is undirected (roads are bidirectional)
"""

from collections import defaultdict
from typing import Optional

import geopandas as gpd
import networkx as nx
import numpy as np
from pyproj import Geod
from scipy.spatial import cKDTree
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
        # O(N log N) using KDTree + union-find instead of the old O(N²) loop.
        sorted_coords = sorted(node_coords)
        n = len(sorted_coords)

        coord_to_node: dict[tuple, int] = {}

        if n == 0:
            pass  # nothing to do
        else:
            coords_arr = np.array(sorted_coords, dtype=np.float64)  # (N, 2)
            tree = cKDTree(coords_arr)

            # Union-Find (path-compressed)
            parent = list(range(n))

            def _find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            # Candidate pairs within the cheap degree bounding box
            candidate_pairs = tree.query_pairs(tolerance_degrees)

            for i, j in candidate_pairs:
                ci = sorted_coords[i]
                cj = sorted_coords[j]
                dist = self._geodesic_distance(ci[0], ci[1], cj[0], cj[1])
                if dist <= self.snap_tolerance_meters:
                    ri, rj = _find(i), _find(j)
                    if ri != rj:
                        parent[ri] = rj

            # Assign integer node IDs: each union root gets a unique ID
            root_to_id: dict[int, int] = {}
            node_id = 0
            for i, coord in enumerate(sorted_coords):
                root = _find(i)
                if root not in root_to_id:
                    root_to_id[root] = node_id
                    node_id += 1
                coord_to_node[coord] = root_to_id[root]

        # Phase 4: Build the graph
        G = nx.Graph()

        # Add all unique nodes with coordinates
        node_coords_by_id = {}
        for coord, nid in coord_to_node.items():
            if nid not in node_coords_by_id:
                node_coords_by_id[nid] = coord

        for nid, coord in node_coords_by_id.items():
            G.add_node(nid, x=coord[0], y=coord[1])

        # Virtual node IDs start after all real nodes so they never collide.
        next_vnode_id = node_id  # node_id was the counter from Phase 3

        # Phase 5: Create edges from LineStrings
        from shapely.ops import substring as _substring

        # Track existing edge weights for deduplication:
        #   edge_weights[(min_node, max_node)] = set of lengths already added
        # Two edges are considered exact duplicates when their lengths differ by
        # less than 1 %.  Exact duplicates arise when the DB returns the same
        # road segment under multiple road_type codes.
        edge_weights: dict[tuple[int, int], set[float]] = {}

        def _is_duplicate(key: tuple[int, int], new_weight: float) -> bool:
            """Return True if an edge with essentially the same length exists."""
            for w in edge_weights.get(key, ()):
                if max(w, new_weight) > 0 and abs(new_weight - w) / max(w, new_weight) < 0.01:
                    return True
            return False

        def _register_weight(key: tuple[int, int], weight: float) -> None:
            edge_weights.setdefault(key, set()).add(weight)

        def _add_virtual_split(
            from_n: int, to_n: int, weight: float, edge_geom: LineString
        ) -> None:
            """Insert a midpoint virtual node to keep a parallel road in the graph."""
            nonlocal next_vnode_id
            mid_pt = edge_geom.interpolate(0.5, normalized=True)
            vnode_id = next_vnode_id
            next_vnode_id += 1
            G.add_node(vnode_id, x=mid_pt.x, y=mid_pt.y)
            try:
                geom_head = _substring(edge_geom, 0.0, 0.5, normalized=True)
                geom_tail = _substring(edge_geom, 0.5, 1.0, normalized=True)
            except Exception:
                cx, cy = mid_pt.x, mid_pt.y
                geom_head = LineString([edge_geom.coords[0], (cx, cy)])
                geom_tail = LineString([(cx, cy), edge_geom.coords[-1]])
            G.add_edge(from_n, vnode_id, weight=weight / 2.0, geometry=geom_head)
            G.add_edge(vnode_id, to_n,   weight=weight / 2.0, geometry=geom_tail)
            # Register both half-weights so a third copy of the same road is
            # also recognised as a duplicate.
            hk1 = (min(from_n, vnode_id), max(from_n, vnode_id))
            hk2 = (min(vnode_id, to_n),   max(vnode_id, to_n))
            _register_weight(hk1, weight / 2.0)
            _register_weight(hk2, weight / 2.0)

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
                        from_node = coord_to_node[current_node_coord]
                        to_node   = coord_to_node[rounded]
                        weight    = self._line_length_meters(segment_coords)
                        edge_geom = LineString(segment_coords)
                        key       = (min(from_node, to_node), max(from_node, to_node))

                        if from_node == to_node:
                            # Self-loop: a cul-de-sac or ring road whose endpoints
                            # both snapped to the same junction.  Inserting a
                            # virtual midpoint node lets the segment stay in the
                            # graph so terminals on it can be mapped correctly.
                            _add_virtual_split(from_node, to_node, weight, edge_geom)

                        elif _is_duplicate(key, weight):
                            # Exact duplicate from DB (same road returned twice
                            # under different road_type codes) — skip silently.
                            pass

                        elif G.has_edge(from_node, to_node):
                            # True parallel road (different geometry / length)
                            # between the same two junctions (e.g. East Parkwood
                            # and West Parkwood).  Keep it via a virtual split.
                            _register_weight(key, weight)
                            _add_virtual_split(from_node, to_node, weight, edge_geom)

                        else:
                            G.add_edge(from_node, to_node,
                                       weight=weight, geometry=edge_geom)
                            _register_weight(key, weight)

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
