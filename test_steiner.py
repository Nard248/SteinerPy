#!/usr/bin/env python3
"""
Standalone test script for the Steiner Network Framework.

Run this script from the project root:
    python test_steiner.py

Or with specific options:
    python test_steiner.py --quick       # Quick test with smallest subset
    python test_steiner.py --benchmark   # Full benchmark
    python test_steiner.py --export      # Quick test with shapefile export
"""
import sys
import os
from pathlib import Path

# Ensure we're running from the project root
PROJECT_ROOT = Path(__file__).parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# Output file for results
OUTPUT_FILE = PROJECT_ROOT / "test_results.txt"


def log(msg: str):
    """Print and log message."""
    print(msg)
    with open(OUTPUT_FILE, 'a') as f:
        f.write(msg + '\n')


def clear_log():
    """Clear the log file."""
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()


def test_imports():
    """Test that all modules can be imported."""
    log("\n" + "="*60)
    log("STEP 1: Testing Imports")
    log("="*60)

    try:
        from src.algorithms.base import AlgorithmRegistry, AlgorithmResult, SteinerAlgorithm
        log("  ✓ base module imported")

        from src.algorithms.mst_based import MSTApproximation, MSTWithSteinerPoints
        log("  ✓ mst_based module imported")

        from src.algorithms.shortest_path import ShortestPathHeuristic, DijkstraSteiner
        log("  ✓ shortest_path module imported")

        from src.algorithms.pruned_dijkstra import PrunedDijkstraSteiner
        log("  ✓ pruned_dijkstra module imported")

        from src.algorithms.genetic import GeneticSteiner
        log("  ✓ genetic module imported")

        log(f"\n  Available algorithms: {AlgorithmRegistry.available_names()}")

        from src.pipeline.runner import SteinerRunner, RunConfig
        log("  ✓ runner module imported")

        from src.pipeline.benchmark import Benchmark, BenchmarkResult
        log("  ✓ benchmark module imported")

        from src.pipeline.exporter import SteinerExporter, quick_export
        log("  ✓ exporter module imported")

        return True
    except Exception as e:
        log(f"  ✗ Import error: {e}")
        import traceback
        log(traceback.format_exc())
        return False


def test_data_loading():
    """Test loading data from subsets."""
    log("\n" + "="*60)
    log("STEP 2: Testing Data Loading")
    log("="*60)

    try:
        from src.pipeline.runner import SteinerRunner

        subset_path = PROJECT_ROOT / "data" / "subsets" / "subset_100"
        roads_path = subset_path / "roads.gpkg"
        locations_path = subset_path / "locations.gpkg"

        if not roads_path.exists():
            log(f"  ✗ Roads file not found: {roads_path}")
            log("  Run create_subsets.py first to generate data.")
            return None

        if not locations_path.exists():
            log(f"  ✗ Locations file not found: {locations_path}")
            return None

        runner = SteinerRunner()
        runner.load_data(str(roads_path), str(locations_path))
        log(f"  ✓ Data loaded")
        log(f"    Roads: {len(runner._roads)} segments")
        log(f"    Locations: {len(runner._locations)} points")

        return runner
    except Exception as e:
        log(f"  ✗ Data loading error: {e}")
        import traceback
        log(traceback.format_exc())
        return None


def test_graph_building(runner):
    """Test building graph from roads."""
    log("\n" + "="*60)
    log("STEP 3: Testing Graph Building")
    log("="*60)

    try:
        runner.build_graph()
        log(f"  ✓ Graph built")
        log(f"    Nodes: {runner.graph.number_of_nodes()}")
        log(f"    Edges: {runner.graph.number_of_edges()}")
        return True
    except Exception as e:
        log(f"  ✗ Graph building error: {e}")
        import traceback
        log(traceback.format_exc())
        return False


def test_terminal_mapping(runner):
    """Test mapping locations to graph terminals."""
    log("\n" + "="*60)
    log("STEP 4: Testing Terminal Mapping")
    log("="*60)

    try:
        runner.map_terminals(max_distance_meters=500)
        log(f"  ✓ Terminals mapped")
        log(f"    Terminal nodes: {len(runner.terminals)}")
        return len(runner.terminals) >= 2
    except Exception as e:
        log(f"  ✗ Terminal mapping error: {e}")
        import traceback
        log(traceback.format_exc())
        return False


def test_algorithms(runner):
    """Test running algorithms."""
    log("\n" + "="*60)
    log("STEP 5: Testing Algorithms")
    log("="*60)

    algorithms = ["mst_approximation", "shortest_path_heuristic", "pruned_dijkstra"]
    results = {}

    for algo_name in algorithms:
        try:
            result = runner.run(algorithm=algo_name)
            results[algo_name] = result
            miles = result.total_weight / 1609.34
            log(f"\n  {algo_name}:")
            log(f"    Total weight: {result.total_weight:.2f} meters ({miles:.2f} miles)")
            log(f"    Execution time: {result.execution_time:.4f} seconds")
            log(f"    Solution nodes: {result.node_count}")
            log(f"    Solution edges: {result.edge_count}")
            log(f"    Steiner points: {len(result.steiner_points)}")
            log(f"    Connected: {result.is_connected}")
        except Exception as e:
            log(f"\n  {algo_name}: ERROR - {e}")
            import traceback
            log(traceback.format_exc())

    return results


def test_export(runner, results):
    """Test shapefile export."""
    log("\n" + "="*60)
    log("STEP 6: Testing Shapefile Export")
    log("="*60)

    try:
        export_dir = PROJECT_ROOT / "exports" / "test_export"
        log(f"  Exporting to: {export_dir}")

        paths = runner.export_debug(results, export_dir, crs="EPSG:4326")

        log(f"  ✓ Export complete!")
        log(f"    Created {len(paths)} files:")
        for name, path in paths.items():
            log(f"      - {name}: {path.name}")

        return True
    except Exception as e:
        log(f"  ✗ Export error: {e}")
        import traceback
        log(traceback.format_exc())
        return False


def run_quick_test(with_export: bool = False):
    """Run a quick test of the framework."""
    clear_log()
    log("="*60)
    log("Steiner Network Framework - Quick Test")
    log("="*60)

    if not test_imports():
        log("\n✗ Import test failed. Fix import errors first.")
        return

    runner = test_data_loading()
    if runner is None:
        log("\n✗ Data loading failed.")
        return

    if not test_graph_building(runner):
        log("\n✗ Graph building failed.")
        return

    if not test_terminal_mapping(runner):
        log("\n✗ Terminal mapping failed or not enough terminals.")
        return

    results = test_algorithms(runner)

    if with_export and results:
        test_export(runner, results)

    log("\n" + "="*60)
    log("TEST COMPLETED!")
    log("="*60)

    if results:
        # Find best algorithm
        best = min(results.items(), key=lambda x: x[1].total_weight if x[1].is_connected else float('inf'))
        miles = best[1].total_weight / 1609.34
        log(f"\nBest algorithm: {best[0]} ({best[1].total_weight:.2f}m / {miles:.2f} miles)")

    log(f"\nResults saved to: {OUTPUT_FILE}")


def run_benchmark(with_export: bool = True):
    """Run full benchmark on all subsets."""
    clear_log()
    log("="*60)
    log("Steiner Network Framework - Full Benchmark")
    log("="*60)

    if not test_imports():
        return

    from src.pipeline.benchmark import Benchmark

    benchmark = Benchmark()
    subsets_dir = PROJECT_ROOT / "data" / "subsets"

    log(f"\nLoading subsets from: {subsets_dir}")
    benchmark.add_subsets_from_directory(str(subsets_dir))

    if not benchmark.subsets:
        log("No subsets found! Run create_subsets.py first.")
        return

    algorithms = ["mst_approximation", "shortest_path_heuristic", "pruned_dijkstra"]

    log(f"\nRunning benchmark with algorithms: {algorithms}")

    if with_export:
        export_dir = PROJECT_ROOT / "exports"
        log(f"Exporting shapefiles to: {export_dir}")
        benchmark.run_with_export(
            algorithms=algorithms,
            max_terminals=100,
            export_dir=str(export_dir),
            crs="EPSG:4326"
        )
    else:
        benchmark.run(algorithms=algorithms, max_terminals=100)

    benchmark.print_summary()

    # Save results
    results_file = PROJECT_ROOT / "benchmark_results.json"
    benchmark.save_results(str(results_file))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--benchmark":
            run_benchmark(with_export=True)
        elif sys.argv[1] == "--quick":
            run_quick_test(with_export=False)
        elif sys.argv[1] == "--export":
            run_quick_test(with_export=True)
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Usage: python test_steiner.py [--quick|--benchmark|--export]")
    else:
        run_quick_test(with_export=False)
