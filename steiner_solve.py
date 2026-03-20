"""
Steiner Tree solver — single entry point.

Accepts a location layer and a road network, builds the graph,
maps terminals, solves, and returns structured results.

Can be imported as a library or run directly:

    from steiner_solve import solve
    result = solve("roads.gpkg", "locations.sqlite")

    # Or with GeoDataFrames
    result = solve(roads_gdf, locations_gdf)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set, Union

import geopandas as gpd
import networkx as nx


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class SteinerResult:
    """Structured output from a Steiner solve run."""

    # Solution graph (nodes have x/y, edges have weight/geometry)
    graph: nx.Graph

    # Node sets
    terminals: Set[int]
    steiner_points: Set[int]

    # Metrics
    total_weight_m: float
    total_weight_mi: float
    node_count: int
    edge_count: int
    is_connected: bool
    execution_time_s: float

    # Algorithm used
    algorithm: str

    # Per-component metadata (from pruned_dijkstra)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # GeoDataFrames ready for export / visualization
    edges_gdf: Optional[gpd.GeoDataFrame] = None
    nodes_gdf: Optional[gpd.GeoDataFrame] = None

    def summary(self) -> str:
        """One-line human-readable summary."""
        return (
            f"{self.algorithm}: {self.total_weight_mi:.2f} mi "
            f"({self.node_count} nodes, {self.edge_count} edges, "
            f"{'connected' if self.is_connected else 'FOREST'}) "
            f"in {self.execution_time_s:.3f}s"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def solve(
    roads: Union[str, Path, gpd.GeoDataFrame],
    locations: Union[str, Path, gpd.GeoDataFrame],
    *,
    algorithm: str = "pruned_dijkstra",
    max_snap_distance_m: float = 200.0,
    connect_forest: bool = True,
    roads_layer: Optional[str] = None,
    locations_layer: Optional[str] = None,
    export_dir: Optional[Union[str, Path]] = None,
    export_format: str = "gpkg",
) -> SteinerResult:
    """
    Run the Steiner tree solver end-to-end.

    Parameters
    ----------
    roads : path or GeoDataFrame
        Road network as LineStrings.  Accepts .gpkg, .shp, .sqlite,
        .geojson, or an in-memory GeoDataFrame.
    locations : path or GeoDataFrame
        Location points to connect.  Same file formats supported.
    algorithm : str
        Algorithm name registered in AlgorithmRegistry.
        Default ``"pruned_dijkstra"`` — fast, forest-aware.
    max_snap_distance_m : float
        Maximum metres a location can be from the nearest road edge
        to still be snapped as a terminal.
    connect_forest : bool
        If the solver returns a disconnected forest, stitch components
        together via shortest paths on the full graph.
    roads_layer / locations_layer : str | None
        Layer name for multi-layer files (GeoPackage, SpatiaLite).
    export_dir : path | None
        If set, export solution edges/nodes here.
    export_format : str
        ``"gpkg"`` or ``"shp"``.

    Returns
    -------
    SteinerResult
        Contains the solution graph, GeoDataFrames, and metrics.
    """
    from src.pipeline.runner import SteinerRunner

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    roads_gdf = _load_geodataframe(roads, layer=roads_layer, label="roads")
    locations_gdf = _load_geodataframe(locations, layer=locations_layer, label="locations")

    print(f"Roads:     {len(roads_gdf)} segments  (CRS {roads_gdf.crs})")
    print(f"Locations: {len(locations_gdf)} points   (CRS {locations_gdf.crs})")

    # ------------------------------------------------------------------
    # 2. Build graph → map terminals → solve
    # ------------------------------------------------------------------
    runner = SteinerRunner()
    runner.load_from_geodataframes(roads_gdf, locations_gdf)
    runner.build_graph()
    runner.map_terminals(max_distance_meters=max_snap_distance_m)

    result = runner.run(algorithm=algorithm)

    # ------------------------------------------------------------------
    # 3. Connect forest if requested
    # ------------------------------------------------------------------
    if connect_forest and not result.is_connected:
        print("  Forest detected — connecting components …")
        result.steiner_graph = _connect_forest(
            result.steiner_graph, runner.graph
        )
        result.node_count = result.steiner_graph.number_of_nodes()
        result.edge_count = result.steiner_graph.number_of_edges()
        result.total_weight = sum(
            d.get("weight", 0)
            for _, _, d in result.steiner_graph.edges(data=True)
        )
        result.is_connected = nx.is_connected(result.steiner_graph)

    # ------------------------------------------------------------------
    # 4. Build output GeoDataFrames
    # ------------------------------------------------------------------
    edges_gdf, nodes_gdf = _build_solution_gdfs(result)

    # ------------------------------------------------------------------
    # 5. Optional export
    # ------------------------------------------------------------------
    if export_dir is not None:
        _export(runner, result, export_dir, export_format)

    # ------------------------------------------------------------------
    # 6. Package result
    # ------------------------------------------------------------------
    sr = SteinerResult(
        graph=result.steiner_graph,
        terminals=result.terminals,
        steiner_points=result.steiner_points,
        total_weight_m=result.total_weight,
        total_weight_mi=result.total_weight / 1609.34,
        node_count=result.node_count,
        edge_count=result.edge_count,
        is_connected=result.is_connected,
        execution_time_s=result.execution_time,
        algorithm=result.algorithm_name,
        metadata=result.metadata,
        edges_gdf=edges_gdf,
        nodes_gdf=nodes_gdf,
    )

    print(f"\n{'─' * 60}")
    print(f"  {sr.summary()}")
    print(f"{'─' * 60}")
    return sr


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_geodataframe(
    source: Union[str, Path, gpd.GeoDataFrame],
    *,
    layer: Optional[str] = None,
    label: str = "",
) -> gpd.GeoDataFrame:
    """Load a GeoDataFrame from a path or pass through if already loaded."""
    if isinstance(source, gpd.GeoDataFrame):
        return source

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")

    if layer is None:
        # Auto-detect layer for multi-layer formats
        try:
            import fiona
            layers = fiona.listlayers(str(path))
            if len(layers) == 1:
                layer = layers[0]
        except Exception:
            pass

    return gpd.read_file(str(path), layer=layer)


def _connect_forest(steiner_graph: nx.Graph, full_graph: nx.Graph) -> nx.Graph:
    """Connect a Steiner forest into a single tree via shortest paths."""
    result = steiner_graph.copy()

    while True:
        components = list(nx.connected_components(result))
        if len(components) <= 1:
            break

        components.sort(key=len, reverse=True)
        main_nodes = components[0]

        dist, paths = nx.multi_source_dijkstra(
            full_graph, main_nodes, weight="weight"
        )

        best_cost = float("inf")
        best_path = None
        for comp in components[1:]:
            for node in comp:
                if node in dist and dist[node] < best_cost:
                    best_cost = dist[node]
                    best_path = paths[node]

        if best_path is None or len(best_path) < 2:
            break

        for u, v in zip(best_path[:-1], best_path[1:]):
            if full_graph.has_edge(u, v):
                result.add_edge(u, v, **full_graph[u][v])
                for n in (u, v):
                    for attr in ("x", "y"):
                        if attr in full_graph.nodes[n]:
                            result.nodes[n][attr] = full_graph.nodes[n][attr]

    return result


def _build_solution_gdfs(result) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Build edges and nodes GeoDataFrames from an AlgorithmResult."""
    from shapely.geometry import LineString, Point

    edge_rows = []
    for u, v, data in result.steiner_graph.edges(data=True):
        if "geometry" in data:
            geom = data["geometry"]
        else:
            ud = result.steiner_graph.nodes[u]
            vd = result.steiner_graph.nodes[v]
            geom = LineString([(ud["x"], ud["y"]), (vd["x"], vd["y"])])
        edge_rows.append(
            {
                "from_node": u,
                "to_node": v,
                "weight_m": data.get("weight", 0.0),
                "weight_mi": data.get("weight", 0.0) / 1609.34,
                "geometry": geom,
            }
        )

    node_rows = []
    for n, data in result.steiner_graph.nodes(data=True):
        if "x" not in data:
            continue
        node_rows.append(
            {
                "node_id": n,
                "type": "terminal" if n in result.terminals else "steiner",
                "geometry": Point(data["x"], data["y"]),
            }
        )

    edges_gdf = gpd.GeoDataFrame(edge_rows, crs="EPSG:4326") if edge_rows else gpd.GeoDataFrame()
    nodes_gdf = gpd.GeoDataFrame(node_rows, crs="EPSG:4326") if node_rows else gpd.GeoDataFrame()
    return edges_gdf, nodes_gdf


def _export(runner, result, export_dir, export_format):
    """Export solution via the runner's exporter."""
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    paths = runner.export_solution(
        result, export_dir, export_format=export_format
    )
    for name, path in paths.items():
        print(f"  Exported {name}: {path}")
