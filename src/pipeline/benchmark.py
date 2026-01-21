"""Benchmarking utilities for Steiner algorithms."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
from datetime import datetime
import pandas as pd
from .runner import SteinerRunner, RunConfig
from ..algorithms.base import AlgorithmRegistry


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""
    subset_name: str
    algorithm: str
    execution_time: float
    total_weight: float
    node_count: int
    edge_count: int
    terminal_count: int
    steiner_point_count: int
    is_connected: bool
    graph_nodes: int
    graph_edges: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subset_name": self.subset_name,
            "algorithm": self.algorithm,
            "execution_time": self.execution_time,
            "total_weight": self.total_weight,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "terminal_count": self.terminal_count,
            "steiner_point_count": self.steiner_point_count,
            "is_connected": self.is_connected,
            "graph_nodes": self.graph_nodes,
            "graph_edges": self.graph_edges,
            "timestamp": self.timestamp,
            **self.metadata
        }


class Benchmark:
    """Benchmarking harness for comparing Steiner algorithms."""

    def __init__(self, config: Optional[RunConfig] = None):
        self.config = config or RunConfig()
        self.subsets: Dict[str, Dict[str, Path]] = {}
        self.results: List[BenchmarkResult] = []

    def add_subset(self, name: str, roads_path: str, locations_path: str) -> "Benchmark":
        self.subsets[name] = {"roads": Path(roads_path), "locations": Path(locations_path)}
        return self

    def add_subsets_from_directory(self, base_dir: str, pattern: str = "subset_*") -> "Benchmark":
        base = Path(base_dir)
        for subset_dir in sorted(base.glob(pattern)):
            if not subset_dir.is_dir():
                continue
            roads_file = locations_file = None
            for ext in [".gpkg", ".shp"]:
                if (subset_dir / f"roads{ext}").exists():
                    roads_file = subset_dir / f"roads{ext}"
                    break
            for ext in [".gpkg", ".sqlite"]:
                if (subset_dir / f"locations{ext}").exists():
                    locations_file = subset_dir / f"locations{ext}"
                    break
            if roads_file and locations_file:
                self.add_subset(subset_dir.name, str(roads_file), str(locations_file))
                print(f"Added subset: {subset_dir.name}")
        return self

    def run(self, algorithms: Optional[List[str]] = None, max_terminals: Optional[int] = None,
            verbose: bool = True, export_shp: bool = False, export_dir_base: Optional[str] = None,
            export_crs: str = "EPSG:4326") -> List[BenchmarkResult]:
        if algorithms is None:
            algorithms = AlgorithmRegistry.available_names()
        if not self.subsets:
            raise ValueError("No subsets added.")

        results = []
        for subset_name, paths in self.subsets.items():
            if verbose:
                print(f"\n{'='*60}\nBenchmarking: {subset_name}\n{'='*60}")

            config = RunConfig(max_terminals=max_terminals)
            runner = SteinerRunner(config)

            try:
                runner.load_data(paths["roads"], paths["locations"])
                runner.build_graph()
                runner.map_terminals()
            except Exception as e:
                print(f"Error loading {subset_name}: {e}")
                continue

            graph_nodes = runner.graph.number_of_nodes()
            graph_edges = runner.graph.number_of_edges()
            terminal_count = len(runner.terminals)

            # Store runner for potential export
            algo_results = {}

            for algo_name in algorithms:
                if verbose:
                    print(f"\n  Running: {algo_name}")
                try:
                    result = runner.run(algorithm=algo_name)
                    algo_results[algo_name] = result
                    results.append(BenchmarkResult(
                        subset_name=subset_name,
                        algorithm=algo_name,
                        execution_time=result.execution_time,
                        total_weight=result.total_weight,
                        node_count=result.node_count,
                        edge_count=result.edge_count,
                        terminal_count=terminal_count,
                        steiner_point_count=len(result.steiner_points),
                        is_connected=result.is_connected,
                        graph_nodes=graph_nodes,
                        graph_edges=graph_edges,
                        metadata=result.metadata
                    ))
                except Exception as e:
                    print(f"    Error: {e}")

            # Export debug shapefiles if requested
            if export_shp and algo_results:
                export_dir = Path(export_dir_base) / subset_name if export_dir_base else Path("exports") / subset_name
                print(f"\n  Exporting shapefiles to: {export_dir}")
                runner.export_debug(algo_results, export_dir, crs=export_crs)

        self.results.extend(results)
        return results

    def run_with_export(
        self,
        algorithms: Optional[List[str]] = None,
        max_terminals: Optional[int] = None,
        export_dir: str = "exports",
        crs: str = "EPSG:4326",
        verbose: bool = True
    ) -> List[BenchmarkResult]:
        """
        Run benchmark and export debug shapefiles for each subset.

        Args:
            algorithms: List of algorithm names
            max_terminals: Maximum terminals per run
            export_dir: Base directory for exports
            crs: Target CRS (EPSG:4326 or ESRI:102008)
            verbose: Print progress

        Returns:
            List of BenchmarkResult objects
        """
        return self.run(
            algorithms=algorithms,
            max_terminals=max_terminals,
            verbose=verbose,
            export_shp=True,
            export_dir_base=export_dir,
            export_crs=crs
        )

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([r.to_dict() for r in self.results])

    def save_results(self, path: str) -> None:
        with open(path, 'w') as f:
            json.dump([r.to_dict() for r in self.results], f, indent=2)
        print(f"Results saved to: {path}")

    def print_summary(self) -> None:
        if not self.results:
            print("No results.")
            return
        df = self.to_dataframe()
        print("\n" + "="*80 + "\nBENCHMARK SUMMARY\n" + "="*80)
        for subset in df['subset_name'].unique():
            sdf = df[df['subset_name'] == subset]
            print(f"\n{subset}: {sdf.iloc[0]['graph_nodes']} nodes, {sdf.iloc[0]['terminal_count']} terminals")
            for _, row in sdf.iterrows():
                t = f"{row['execution_time']:.4f}" if row['execution_time'] >= 0 else "ERROR"
                w = f"{row['total_weight']:.2f}" if row['total_weight'] < float('inf') else "INF"
                mi = row['total_weight'] / 1609.34  # Convert to miles
                print(f"  {row['algorithm']:<25} {t:<10}s {w:<12}m ({mi:.2f} mi) {row['is_connected']}")
