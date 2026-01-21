#!/usr/bin/env python3
"""Steiner Network Benchmark Runner"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.algorithms.base import AlgorithmRegistry
from src.algorithms.mst_based import MSTApproximation, MSTWithSteinerPoints
from src.algorithms.shortest_path import ShortestPathHeuristic, DijkstraSteiner
from src.algorithms.pruned_dijkstra import PrunedDijkstraSteiner
from src.algorithms.genetic import GeneticSteiner
from src.pipeline.runner import SteinerRunner, RunConfig
from src.pipeline.benchmark import Benchmark, BenchmarkResult


def quick_test():
    """Quick test with single subset."""
    print("="*70)
    print("Quick Test - Single Subset")
    print("="*70)

    print("\nAvailable algorithms:", AlgorithmRegistry.available_names())

    subsets_dir = Path(__file__).parent / "data" / "subsets" / "subset_100"
    roads_path = subsets_dir / "roads.gpkg"
    locations_path = subsets_dir / "locations.gpkg"

    if not roads_path.exists():
        print(f"Subset not found at {subsets_dir}")
        print("Run create_subsets.py first.")
        return

    runner = SteinerRunner()
    runner.load_data(roads_path, locations_path)
    runner.build_graph()
    runner.map_terminals(max_distance_meters=500)

    print(f"\nTerminals mapped: {len(runner.terminals)}")
    if len(runner.terminals) < 2:
        print("Not enough terminals. Try increasing max_distance_meters.")
        return

    print("\nRunning algorithms...")
    for algo in ["mst_approximation", "shortest_path_heuristic", "pruned_dijkstra"]:
        try:
            result = runner.run(algorithm=algo)
            print(f"\n{algo}: {result.total_weight:.2f}m in {result.execution_time:.4f}s")
        except Exception as e:
            print(f"\n{algo}: Error - {e}")


def main():
    print("="*70)
    print("Steiner Network Algorithm Benchmark")
    print("="*70)

    print("\nAvailable algorithms:")
    for algo in AlgorithmRegistry.list_algorithms():
        exact = "[EXACT]" if algo['is_exact'] else "[APPROX]"
        print(f"  - {algo['name']:<25} {exact:<10} {algo['description']}")

    benchmark = Benchmark()
    subsets_dir = Path(__file__).parent / "data" / "subsets"
    print(f"\nLoading subsets from: {subsets_dir}")
    benchmark.add_subsets_from_directory(str(subsets_dir))

    if not benchmark.subsets:
        print("No subsets found! Run create_subsets.py first.")
        return

    algorithms = ["mst_approximation", "shortest_path_heuristic", "pruned_dijkstra"]

    # Run on smallest subsets first
    subset_names = sorted(benchmark.subsets.keys())[:2]
    for name in subset_names:
        paths = benchmark.subsets[name]
        temp_bench = Benchmark()
        temp_bench.add_subset(name, str(paths["roads"]), str(paths["locations"]))
        temp_bench.run(algorithms=algorithms, max_terminals=50)
        benchmark.results.extend(temp_bench.results)

    benchmark.print_summary()
    results_path = Path(__file__).parent / "benchmark_results.json"
    benchmark.save_results(str(results_path))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        quick_test()
    else:
        main()
