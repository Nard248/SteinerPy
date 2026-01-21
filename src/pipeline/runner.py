"""Configurable runner for Steiner Network algorithms."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
import time

import geopandas as gpd
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from ..data.graph_builder import GraphBuilder
from ..algorithms.base import AlgorithmRegistry, AlgorithmResult


@dataclass
class RunConfig:
    """Configuration for a Steiner algorithm run."""
    algorithm: str = "mst_approximation"
    algorithm_params: Dict[str, Any] = field(default_factory=dict)
    coord_precision: int = 6
    snap_tolerance_meters: float = 1.0
    max_terminals: Optional[int] = None
    terminal_sample_seed: int = 42
    save_results: bool = True
    output_dir: Optional[str] = None


class SteinerRunner:
    """Main runner class for Steiner Network operations."""

    def __init__(self, config: Optional[RunConfig] = None):
        self.config = config or RunConfig()
        self.graph_builder = GraphBuilder(
            coord_precision=self.config.coord_precision,
            snap_tolerance_meters=self.config.snap_tolerance_meters
        )
        self._graph: Optional[nx.Graph] = None
        self._locations: Optional[gpd.GeoDataFrame] = None
        self._roads: Optional[gpd.GeoDataFrame] = None
        self._terminals: Optional[Set[int]] = None
        self._location_to_node: Optional[Dict[int, int]] = None

    @property
    def graph(self) -> Optional[nx.Graph]:
        return self._graph

    @property
    def terminals(self) -> Optional[Set[int]]:
        return self._terminals

    def load_data(self, roads_path: Union[str, Path], locations_path: Union[str, Path],
                  roads_layer: Optional[str] = None, locations_layer: Optional[str] = None) -> "SteinerRunner":
        print(f"Loading roads from: {roads_path}")
        self._roads = gpd.read_file(roads_path, layer=roads_layer)
        print(f"  Loaded {len(self._roads)} road segments")

        print(f"Loading locations from: {locations_path}")
        self._locations = gpd.read_file(locations_path, layer=locations_layer)
        print(f"  Loaded {len(self._locations)} locations")

        if self._roads.crs != self._locations.crs:
            print(f"  Reprojecting locations to match roads CRS")
            self._locations = self._locations.to_crs(self._roads.crs)
        return self

    def load_from_geodataframes(self, roads: gpd.GeoDataFrame, locations: gpd.GeoDataFrame) -> "SteinerRunner":
        self._roads = roads.copy()
        self._locations = locations.copy()
        if self._roads.crs != self._locations.crs and self._roads.crs is not None:
            self._locations = self._locations.to_crs(self._roads.crs)
        return self

    def build_graph(self) -> "SteinerRunner":
        if self._roads is None:
            raise ValueError("No road data loaded. Call load_data() first.")

        print("Building graph from road network...")
        start_time = time.perf_counter()
        self._graph, report = self.graph_builder.build_and_validate(self._roads)
        elapsed = time.perf_counter() - start_time

        print(f"  Built graph in {elapsed:.2f}s")
        print(f"  Nodes: {report['node_count']}, Edges: {report['edge_count']}")
        print(f"  Connected components: {report['connected_components']}")
        if not report['valid']:
            print(f"  Warning: {report['issues']}")
        return self

    def map_terminals(self, max_distance_meters: float = 100.0) -> "SteinerRunner":
        if self._graph is None:
            raise ValueError("No graph built. Call build_graph() first.")
        if self._locations is None:
            raise ValueError("No location data loaded.")

        print("Mapping locations to graph nodes...")
        node_coords = {n: (self._graph.nodes[n]['x'], self._graph.nodes[n]['y'])
                       for n in self._graph.nodes() if 'x' in self._graph.nodes[n]}

        node_ids = list(node_coords.keys())
        coords_array = np.array([node_coords[n] for n in node_ids])
        tree = cKDTree(coords_array)

        self._location_to_node = {}
        self._terminals = set()
        max_dist_deg = max_distance_meters / 111000

        for idx, row in self._locations.iterrows():
            if row.geometry is None:
                continue
            loc_coord = (row.geometry.x, row.geometry.y)
            dist, nearest_idx = tree.query(loc_coord)
            if dist <= max_dist_deg:
                node_id = node_ids[nearest_idx]
                self._location_to_node[idx] = node_id
                self._terminals.add(node_id)

        print(f"  Mapped {len(self._location_to_node)} locations to {len(self._terminals)} unique nodes")

        if self.config.max_terminals and len(self._terminals) > self.config.max_terminals:
            import random
            random.seed(self.config.terminal_sample_seed)
            self._terminals = set(random.sample(list(self._terminals), self.config.max_terminals))
            print(f"  Limited to {len(self._terminals)} terminals")
        return self

    def set_terminals(self, terminals: Set[int]) -> "SteinerRunner":
        if self._graph is None:
            raise ValueError("No graph built.")
        invalid = terminals - set(self._graph.nodes())
        if invalid:
            raise ValueError(f"Invalid terminal nodes: {invalid}")
        self._terminals = terminals
        return self

    def run(self, algorithm: Optional[str] = None, **algorithm_params) -> AlgorithmResult:
        if self._graph is None:
            raise ValueError("No graph built.")
        if not self._terminals:
            raise ValueError("No terminals mapped.")

        algo_name = algorithm or self.config.algorithm
        params = {**self.config.algorithm_params, **algorithm_params}

        print(f"\nRunning algorithm: {algo_name}")
        print(f"  Terminals: {len(self._terminals)}, Graph: {self._graph.number_of_nodes()} nodes")

        algo = AlgorithmRegistry.create(algo_name, **params)
        result = algo.solve(self._graph, self._terminals)

        print(f"\nResult: {result.total_weight:.2f}m in {result.execution_time:.4f}s")
        print(f"  Nodes: {result.node_count}, Edges: {result.edge_count}, Connected: {result.is_connected}")
        return result

    def run_all(self, algorithms: Optional[List[str]] = None) -> Dict[str, AlgorithmResult]:
        if algorithms is None:
            algorithms = AlgorithmRegistry.available_names()
        results = {}
        for algo_name in algorithms:
            try:
                results[algo_name] = self.run(algorithm=algo_name)
            except Exception as e:
                print(f"  Error running {algo_name}: {e}")
        return results

    def get_solution_gdf(self, result: AlgorithmResult) -> gpd.GeoDataFrame:
        from shapely.geometry import LineString
        edges_data = []
        for u, v, data in result.steiner_graph.edges(data=True):
            if 'geometry' in data:
                geom = data['geometry']
            else:
                u_data, v_data = result.steiner_graph.nodes[u], result.steiner_graph.nodes[v]
                geom = LineString([(u_data['x'], u_data['y']), (v_data['x'], v_data['y'])])
            edges_data.append({
                'from_node': u, 'to_node': v, 'weight': data.get('weight', 0),
                'is_terminal_edge': u in result.terminals or v in result.terminals,
                'geometry': geom
            })
        return gpd.GeoDataFrame(edges_data, crs=self._roads.crs if self._roads else None)

    def export_debug(
        self,
        results: Dict[str, AlgorithmResult],
        output_dir: Union[str, Path],
        crs: str = "EPSG:4326",
        export_format: str = "shp",
        include_full_graph: bool = True
    ) -> Dict[str, Path]:
        """
        Export debug shapefiles for graph, terminals, and all solutions.

        Creates the following layers:
        - graph_nodes: All road network nodes (with terminal markers)
        - graph_edges: All road network edges (full road network)
        - terminals: Terminal/snap points
        - solution_<algo>_edges: Solution edges for each algorithm
        - solution_<algo>_nodes: Solution nodes for each algorithm
        - mileage_summary.csv: Distance statistics per algorithm

        Args:
            results: Dict mapping algorithm name to AlgorithmResult
            output_dir: Output directory path
            crs: Target CRS (EPSG:4326 or ESRI:102008)
            export_format: Output format ('shp' for Shapefile, 'gpkg' for GeoPackage)
            include_full_graph: Whether to include full road network (can be large)

        Returns:
            Dict with paths to all created files
        """
        from .exporter import SteinerExporter

        exporter = SteinerExporter(output_dir, crs=crs, export_format=export_format)
        return exporter.export_full_debug_package(
            graph=self._graph,
            terminals=self._terminals,
            results=results,
            location_mapping=self._location_to_node,
            include_full_graph=include_full_graph
        )

    def export_solution(
        self,
        result: AlgorithmResult,
        output_dir: Union[str, Path],
        crs: str = "EPSG:4326",
        export_format: str = "shp",
        filename_prefix: str = "solution"
    ) -> Dict[str, Path]:
        """
        Export a single solution to shapefiles.

        Args:
            result: AlgorithmResult to export
            output_dir: Output directory path
            crs: Target CRS (EPSG:4326 or ESRI:102008)
            export_format: Output format ('shp' for Shapefile, 'gpkg' for GeoPackage)
            filename_prefix: Prefix for output files

        Returns:
            Dict with paths to created files
        """
        from .exporter import SteinerExporter

        exporter = SteinerExporter(output_dir, crs=crs, export_format=export_format)
        return exporter.export_solution(result, self._graph, filename_prefix)

