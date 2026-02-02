"""
SteinerPipeline: Clean, configurable interface for Steiner Network operations.

This module provides a staged pipeline for:
1. Data loading (road networks, locations)
2. Graph construction with validation
3. Terminal mapping (snap locations to graph)
4. Algorithm execution (single or benchmark all)
5. Result export (shapefiles, debug layers, mileage reports)

Example usage:
    >>> from src.pipeline import SteinerPipeline
    >>>
    >>> # Quick usage
    >>> pipeline = SteinerPipeline()
    >>> results = pipeline.run_from_files(
    ...     roads_path="data/roads.gpkg",
    ...     locations_path="data/locations.gpkg",
    ...     algorithm="mst_approximation"
    ... )
    >>>
    >>> # Staged usage with full control
    >>> pipeline = SteinerPipeline()
    >>> pipeline.load_data(roads_path, locations_path)
    >>> pipeline.build_graph()
    >>> pipeline.map_terminals(max_distance_meters=50.0)
    >>> result = pipeline.run(algorithm="mst_approximation")
    >>> pipeline.export_debug(results, output_dir="./output", crs="EPSG:4326")
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import time
import math
import json

import geopandas as gpd
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from pyproj import Geod
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree

from ..data.graph_builder import GraphBuilder
from ..algorithms.base import AlgorithmRegistry, AlgorithmResult
from ..graph_cache.graph_cache import GraphCache


@dataclass
class PipelineConfig:
    """Configuration for the Steiner pipeline."""

    # Graph building
    coord_precision: int = 6
    snap_tolerance_meters: float = 1.0

    # Terminal mapping
    max_snap_distance_meters: float = 100.0

    # Algorithm defaults
    default_algorithm: str = "mst_approximation"

    # Export settings
    default_crs: str = "EPSG:4326"
    export_format: str = "shp"  # 'shp' or 'gpkg'

    # Limits
    max_terminals: Optional[int] = None
    terminal_sample_seed: int = 42


@dataclass
class PipelineState:
    """Tracks the current state of the pipeline."""
    data_loaded: bool = False
    graph_built: bool = False
    terminals_mapped: bool = False

    # Data
    roads: Optional[gpd.GeoDataFrame] = None
    locations: Optional[gpd.GeoDataFrame] = None
    graph: Optional[nx.Graph] = None
    graph_report: Optional[Dict] = None
    terminals: Optional[Set[int]] = None
    location_to_node: Optional[Dict[int, int]] = None

    # Timing
    load_time: float = 0.0
    build_time: float = 0.0
    map_time: float = 0.0


class SteinerPipeline:
    """
    Main pipeline class for Steiner Network operations.

    Provides a clean, staged interface for running Steiner algorithms
    on road networks. Supports both quick one-shot usage and detailed
    step-by-step control.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize the pipeline with optional configuration."""
        self.config = config or PipelineConfig()
        self._state = PipelineState()
        self._graph_builder = GraphBuilder(
            coord_precision=self.config.coord_precision,
            snap_tolerance_meters=self.config.snap_tolerance_meters
        )
        self._results: Dict[str, AlgorithmResult] = {}

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def graph(self) -> Optional[nx.Graph]:
        """The constructed road network graph."""
        return self._state.graph

    @property
    def terminals(self) -> Optional[Set[int]]:
        """Set of terminal node IDs."""
        return self._state.terminals

    @property
    def roads(self) -> Optional[gpd.GeoDataFrame]:
        """Loaded road network GeoDataFrame."""
        return self._state.roads

    @property
    def locations(self) -> Optional[gpd.GeoDataFrame]:
        """Loaded locations GeoDataFrame."""
        return self._state.locations

    @property
    def results(self) -> Dict[str, AlgorithmResult]:
        """Dictionary of algorithm results from last run."""
        return self._results

    @property
    def is_ready(self) -> bool:
        """Whether the pipeline is ready to run algorithms."""
        return (self._state.data_loaded and
                self._state.graph_built and
                self._state.terminals_mapped)

    # =========================================================================
    # Stage 1: Data Loading
    # =========================================================================

    def load_data(
        self,
        roads_path: Union[str, Path],
        locations_path: Union[str, Path],
        roads_layer: Optional[str] = None,
        locations_layer: Optional[str] = None
    ) -> "SteinerPipeline":
        """
        Load road network and location data from files.

        Args:
            roads_path: Path to road network file (shapefile, geopackage, etc.)
            locations_path: Path to locations file
            roads_layer: Optional layer name for geopackage
            locations_layer: Optional layer name for geopackage

        Returns:
            Self for method chaining.
        """
        start = time.perf_counter()

        print(f"[Stage 1] Loading data...")
        print(f"  Roads: {roads_path}")
        self._state.roads = gpd.read_file(roads_path, layer=roads_layer)
        print(f"    -> {len(self._state.roads)} road segments")

        print(f"  Locations: {locations_path}")
        self._state.locations = gpd.read_file(locations_path, layer=locations_layer)
        print(f"    -> {len(self._state.locations)} locations")

        # Ensure CRS match
        if self._state.roads.crs != self._state.locations.crs:
            print(f"  Reprojecting locations to match roads CRS ({self._state.roads.crs})")
            self._state.locations = self._state.locations.to_crs(self._state.roads.crs)

        self._state.load_time = time.perf_counter() - start
        self._state.data_loaded = True
        print(f"  Data loaded in {self._state.load_time:.2f}s")

        return self

    def load_from_geodataframes(
        self,
        roads: gpd.GeoDataFrame,
        locations: gpd.GeoDataFrame
    ) -> "SteinerPipeline":
        """
        Load data from existing GeoDataFrames.

        Args:
            roads: Road network GeoDataFrame
            locations: Locations GeoDataFrame

        Returns:
            Self for method chaining.
        """
        start = time.perf_counter()

        self._state.roads = roads.copy()
        self._state.locations = locations.copy()

        if self._state.roads.crs != self._state.locations.crs and self._state.roads.crs is not None:
            self._state.locations = self._state.locations.to_crs(self._state.roads.crs)

        self._state.load_time = time.perf_counter() - start
        self._state.data_loaded = True

        return self

    # =========================================================================
    # Stage 2: Graph Building
    # =========================================================================

    def build_graph(self) -> "SteinerPipeline":
        """
        Build NetworkX graph from road network.

        The graph construction:
        1. Extracts all LineString geometries
        2. Identifies vertices (endpoints + intersections)
        3. Creates edges with geodesic distances as weights
        4. Validates the graph structure

        Returns:
            Self for method chaining.

        Raises:
            ValueError: If no road data is loaded.
        """

        cache = GraphCache()

        graph, report = cache.get_or_build(
            roads_gdf=self._state.roads,
            builder=self._graph_builder
        )

        self._state.graph = graph
        self._state.graph_report = report

        if not self._state.data_loaded:
            raise ValueError("No data loaded. Call load_data() first.")

        start = time.perf_counter()
        print(f"\n[Stage 2] Building graph...")

        cache = GraphCache()

        self._state.graph, self._state.graph_report = cache.get_or_build(
            roads_gdf=self._state.roads,
            builder=self._graph_builder,
        )


        self._state.build_time = time.perf_counter() - start
        self._state.graph_built = True

        report = self._state.graph_report
        print(f"  Nodes: {report['node_count']:,}")
        print(f"  Edges: {report['edge_count']:,}")
        print(f"  Connected components: {report['connected_components']}")

        if not report['valid']:
            print(f"  Warnings: {report['issues']}")

        print(f"  Built in {self._state.build_time:.2f}s")

        return self

    # =========================================================================
    # Stage 3: Terminal Mapping
    # =========================================================================

    def map_terminals(
        self,
        max_distance_meters: Optional[float] = None
    ) -> "SteinerPipeline":
        """
        Map location points to nearest road edges, then snap to nearest endpoint node.

        This version is Shapely 2.x safe and avoids graph fragmentation
        caused by node-only snapping.
        """
        if not self._state.graph_built:
            raise ValueError("Graph not built. Call build_graph() first.")

        from shapely.geometry import Point
        from shapely.strtree import STRtree

        max_dist = max_distance_meters or self.config.max_snap_distance_meters

        start = time.perf_counter()
        print(f"\n[Stage 3] Mapping terminals (edge snapping, max distance: {max_dist}m)...")

        graph = self._state.graph

        # ------------------------------------------------------------------
        # Build spatial index over edge geometries
        # ------------------------------------------------------------------
        edge_geoms = []
        edge_nodes = []  # (u, v) per geometry

        for u, v, data in graph.edges(data=True):
            geom = data.get("geometry")
            if geom is None:
                continue
            edge_geoms.append(geom)
            edge_nodes.append((u, v))

        if not edge_geoms:
            raise ValueError("Graph has no edge geometries; cannot snap terminals.")

        tree = STRtree(edge_geoms)

        self._state.location_to_node = {}
        self._state.terminals = set()

        snapped = 0
        skipped = 0

        # ------------------------------------------------------------------
        # Snap each location
        # ------------------------------------------------------------------
        for idx, row in self._state.locations.iterrows():
            if row.geometry is None:
                skipped += 1
                continue

            pt = row.geometry

            # STRtree.query returns INDICES in Shapely >= 2.0
            candidate_idxs = tree.query(pt.buffer(max_dist))

            if len(candidate_idxs) == 0:
                skipped += 1
                continue

            best_i = None
            best_dist = float("inf")

            for i in candidate_idxs:
                geom = edge_geoms[int(i)]
                d = geom.distance(pt)
                if d < best_dist:
                    best_dist = d
                    best_i = int(i)

            if best_i is None:
                skipped += 1
                continue

            # Snap to nearest endpoint of the best edge
            u, v = edge_nodes[best_i]

            ux, uy = graph.nodes[u]["x"], graph.nodes[u]["y"]
            vx, vy = graph.nodes[v]["x"], graph.nodes[v]["y"]

            du = Point(ux, uy).distance(pt)
            dv = Point(vx, vy).distance(pt)

            node = u if du <= dv else v

            self._state.location_to_node[idx] = node
            self._state.terminals.add(node)
            snapped += 1

        print(f"  Snapped: {snapped} locations -> {len(self._state.terminals)} unique nodes")
        if skipped > 0:
            print(f"  Skipped: {skipped} locations (too far from roads)")

        # ------------------------------------------------------------------
        # Optional terminal limiting
        # ------------------------------------------------------------------
        if self.config.max_terminals and len(self._state.terminals) > self.config.max_terminals:
            import random
            random.seed(self.config.terminal_sample_seed)
            self._state.terminals = set(
                random.sample(list(self._state.terminals), self.config.max_terminals)
            )
            print(f"  Limited to {len(self._state.terminals)} terminals (config.max_terminals)")

        self._state.map_time = time.perf_counter() - start
        self._state.terminals_mapped = True
        print(f"  Mapped in {self._state.map_time:.3f}s")

        return self

    def set_terminals(self, terminals: Set[int]) -> "SteinerPipeline":
        """
        Manually set terminal nodes (bypasses automatic mapping).

        Args:
            terminals: Set of node IDs that must be connected.

        Returns:
            Self for method chaining.
        """
        if not self._state.graph_built:
            raise ValueError("Graph not built. Call build_graph() first.")

        invalid = terminals - set(self._state.graph.nodes())
        if invalid:
            raise ValueError(f"Invalid terminal nodes (not in graph): {invalid}")

        self._state.terminals = set(terminals)
        self._state.terminals_mapped = True

        return self

    # =========================================================================
    # Stage 4: Algorithm Execution
    # =========================================================================

    def run(
        self,
        algorithm: Optional[str] = None,
        **algorithm_params
    ) -> AlgorithmResult:
        """
        Run a single Steiner algorithm.

        Args:
            algorithm: Algorithm name (see available_algorithms()).
                       Defaults to config.default_algorithm.
            **algorithm_params: Algorithm-specific parameters.

        Returns:
            AlgorithmResult with the Steiner tree solution.
        """
        if not self.is_ready:
            raise ValueError("Pipeline not ready. Complete all stages first.")

        algo_name = algorithm or self.config.default_algorithm

        print(f"\n[Run] Algorithm: {algo_name}")
        print(f"  Graph: {self._state.graph.number_of_nodes():,} nodes, "
              f"{self._state.graph.number_of_edges():,} edges")
        print(f"  Terminals: {len(self._state.terminals)}")

        algo = AlgorithmRegistry.create(algo_name, **algorithm_params)
        result = algo.solve(self._state.graph, self._state.terminals)

        self._results[algo_name] = result

        print(f"\n  Result:")
        print(f"    Total distance: {result.total_weight:,.2f}m "
              f"({result.total_weight/1000:.2f}km, {result.total_weight/1609.34:.2f}mi)")
        print(f"    Nodes: {result.node_count}, Edges: {result.edge_count}")
        print(f"    Steiner points: {len(result.steiner_points)}")
        print(f"    Connected: {result.is_connected}")
        print(f"    Time: {result.execution_time:.4f}s")

        return result

    def run_all(
        self,
        algorithms: Optional[List[str]] = None
    ) -> Dict[str, AlgorithmResult]:
        """
        Run multiple algorithms for benchmarking.

        Args:
            algorithms: List of algorithm names. If None, runs all registered.

        Returns:
            Dict mapping algorithm name to AlgorithmResult.
        """
        if not self.is_ready:
            raise ValueError("Pipeline not ready. Complete all stages first.")

        if algorithms is None:
            algorithms = self.available_algorithms()

        print(f"\n[Benchmark] Running {len(algorithms)} algorithms...")
        print("=" * 60)

        self._results = {}

        for algo_name in algorithms:
            try:
                result = self.run(algorithm=algo_name)
                self._results[algo_name] = result
            except Exception as e:
                print(f"  ERROR in {algo_name}: {e}")

        # Print summary
        self._print_benchmark_summary()

        return self._results

    def _print_benchmark_summary(self):
        """Print a formatted benchmark summary table."""
        if not self._results:
            return

        print("\n" + "=" * 80)
        print("BENCHMARK SUMMARY")
        print("=" * 80)

        # Sort by total weight
        sorted_results = sorted(
            self._results.items(),
            key=lambda x: x[1].total_weight if x[1].total_weight < float('inf') else float('inf')
        )

        best_weight = sorted_results[0][1].total_weight if sorted_results else 0

        header = f"{'Algorithm':<25} {'Distance':>12} {'Nodes':>8} {'Edges':>8} {'Time':>10} {'vs Best':>10}"
        print(header)
        print("-" * 80)

        for algo_name, result in sorted_results:
            if result.total_weight == float('inf'):
                dist_str = "FAILED"
                pct_str = "-"
            else:
                dist_str = f"{result.total_weight/1000:.2f}km"
                if best_weight > 0:
                    pct = ((result.total_weight - best_weight) / best_weight) * 100
                    pct_str = f"+{pct:.1f}%" if pct > 0 else "BEST"
                else:
                    pct_str = "-"

            row = (f"{algo_name:<25} {dist_str:>12} {result.node_count:>8} "
                   f"{result.edge_count:>8} {result.execution_time:>9.3f}s {pct_str:>10}")
            print(row)

        print("=" * 80)

    # =========================================================================
    # Stage 5: Export
    # =========================================================================

    def export_debug(
        self,
        results: Optional[Dict[str, AlgorithmResult]] = None,
        output_dir: Union[str, Path] = "./steiner_output",
        crs: Optional[str] = None,
        export_format: Optional[str] = None,
        include_full_graph: bool = True
    ) -> Dict[str, Path]:
        """
        Export full debug package with all layers.

        Creates:
        - graph_nodes: All road network nodes (with terminal markers)
        - graph_edges: All road network edges
        - terminals: Terminal/snap points
        - solution_<algo>_edges: Solution edges per algorithm
        - solution_<algo>_nodes: Solution nodes per algorithm
        - mileage_summary.csv: Distance statistics

        Args:
            results: Results to export. Defaults to last run results.
            output_dir: Output directory path.
            crs: Target CRS (EPSG:4326 or ESRI:102008). Defaults to config.
            export_format: 'shp' or 'gpkg'. Defaults to config.
            include_full_graph: Whether to export full road network.

        Returns:
            Dict mapping layer names to file paths.
        """
        from .exporter import SteinerExporter

        results = results or self._results
        if not results:
            raise ValueError("No results to export. Run an algorithm first.")

        crs = crs or self.config.default_crs
        export_format = export_format or self.config.export_format

        print(f"\n[Export] Creating debug package...")
        print(f"  Output: {output_dir}")
        print(f"  CRS: {crs}")
        print(f"  Format: {export_format}")

        exporter = SteinerExporter(output_dir, crs=crs, export_format=export_format)

        paths = exporter.export_full_debug_package(
            graph=self._state.graph,
            terminals=self._state.terminals,
            results=results,
            location_mapping=self._state.location_to_node,
            include_full_graph=include_full_graph
        )

        return paths

    def export_solution(
        self,
        result: AlgorithmResult,
        output_dir: Union[str, Path],
        crs: Optional[str] = None,
        filename_prefix: str = "solution"
    ) -> Dict[str, Path]:
        """Export a single solution to shapefiles."""
        from .exporter import SteinerExporter

        crs = crs or self.config.default_crs
        exporter = SteinerExporter(
            output_dir,
            crs=crs,
            export_format=self.config.export_format
        )

        return exporter.export_solution(result, self._state.graph, filename_prefix)

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    def run_from_files(
        self,
        roads_path: Union[str, Path],
        locations_path: Union[str, Path],
        algorithm: Optional[str] = None,
        max_snap_distance: Optional[float] = None,
        roads_layer: Optional[str] = None,
        locations_layer: Optional[str] = None,
        **algorithm_params
    ) -> AlgorithmResult:
        """
        One-shot method: load data, build graph, map terminals, and run algorithm.

        Args:
            roads_path: Path to road network file.
            locations_path: Path to locations file.
            algorithm: Algorithm to run. Defaults to config.default_algorithm.
            max_snap_distance: Maximum snap distance in meters.
            roads_layer: Optional layer name for geopackage.
            locations_layer: Optional layer name for geopackage.
            **algorithm_params: Algorithm-specific parameters.

        Returns:
            AlgorithmResult from the algorithm.
        """
        self.load_data(roads_path, locations_path, roads_layer, locations_layer)
        self.build_graph()
        self.map_terminals(max_snap_distance)
        return self.run(algorithm, **algorithm_params)

    def benchmark_from_files(
        self,
        roads_path: Union[str, Path],
        locations_path: Union[str, Path],
        algorithms: Optional[List[str]] = None,
        max_snap_distance: Optional[float] = None,
        output_dir: Optional[Union[str, Path]] = None
    ) -> Dict[str, AlgorithmResult]:
        """
        One-shot benchmark: load, build, map, run all algorithms, optionally export.

        Args:
            roads_path: Path to road network file.
            locations_path: Path to locations file.
            algorithms: Algorithms to run. If None, runs all.
            max_snap_distance: Maximum snap distance in meters.
            output_dir: If provided, exports debug package to this directory.

        Returns:
            Dict mapping algorithm name to AlgorithmResult.
        """
        self.load_data(roads_path, locations_path)
        self.build_graph()
        self.map_terminals(max_snap_distance)
        results = self.run_all(algorithms)

        if output_dir:
            self.export_debug(results, output_dir)

        return results

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @staticmethod
    def available_algorithms() -> List[str]:
        """Get list of available algorithm names."""
        return AlgorithmRegistry.available_names()

    @staticmethod
    def fast_algorithms() -> List[str]:
        """Get list of fast algorithms suitable for large datasets."""
        return [
            "mst_approximation",
            "pruned_dijkstra",
            "dijkstra_steiner",  # Falls back to heuristic for >12 terminals
        ]

    @staticmethod
    def exclude_algorithms(exclude: List[str]) -> List[str]:
        """Get all algorithms except the excluded ones."""
        return [a for a in AlgorithmRegistry.available_names() if a not in exclude]

    @staticmethod
    def algorithm_info() -> List[Dict[str, Any]]:
        """Get detailed info about all registered algorithms."""
        return AlgorithmRegistry.list_algorithms()

    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current pipeline state."""
        return {
            "data_loaded": self._state.data_loaded,
            "graph_built": self._state.graph_built,
            "terminals_mapped": self._state.terminals_mapped,
            "is_ready": self.is_ready,
            "road_segments": len(self._state.roads) if self._state.roads is not None else 0,
            "locations": len(self._state.locations) if self._state.locations is not None else 0,
            "graph_nodes": self._state.graph.number_of_nodes() if self._state.graph else 0,
            "graph_edges": self._state.graph.number_of_edges() if self._state.graph else 0,
            "terminals": len(self._state.terminals) if self._state.terminals else 0,
            "timing": {
                "load_time": self._state.load_time,
                "build_time": self._state.build_time,
                "map_time": self._state.map_time
            }
        }

    def get_mileage_report(self) -> Dict[str, Dict[str, float]]:
        """
        Get mileage report for all results.

        Returns:
            Dict mapping algorithm name to distance metrics.
        """
        report = {}

        for algo_name, result in self._results.items():
            meters = result.total_weight
            report[algo_name] = {
                "meters": meters,
                "kilometers": meters / 1000.0,
                "miles": meters / 1609.34,
                "feet": meters * 3.28084
            }

        return report

    def reset(self) -> "SteinerPipeline":
        """Reset the pipeline state, keeping configuration."""
        self._state = PipelineState()
        self._results = {}
        return self
