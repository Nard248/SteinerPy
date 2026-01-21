#!/usr/bin/env python3
"""Simple test script for Steiner algorithms."""
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

# Log to file
log_file = Path(__file__).parent / "test_output.log"
log = open(log_file, 'w')

def write(msg):
    print(msg)
    log.write(msg + '\n')
    log.flush()

write("="*60)
write("Testing Steiner Network Framework")
write("="*60)

try:
    write("\n1. Importing modules...")
    from src.algorithms.base import AlgorithmRegistry
    from src.algorithms.mst_based import MSTApproximation, MSTWithSteinerPoints
    from src.algorithms.shortest_path import ShortestPathHeuristic, DijkstraSteiner
    from src.algorithms.pruned_dijkstra import PrunedDijkstraSteiner
    from src.algorithms.genetic import GeneticSteiner
    write(f"   Available algorithms: {AlgorithmRegistry.available_names()}")

    write("\n2. Importing pipeline...")
    from src.pipeline.runner import SteinerRunner, RunConfig
    write("   SteinerRunner imported OK")

    write("\n3. Loading data...")
    runner = SteinerRunner()
    runner.load_data(
        str(Path(__file__).parent / "data/subsets/subset_100/roads.gpkg"),
        str(Path(__file__).parent / "data/subsets/subset_100/locations.gpkg")
    )

    write("\n4. Building graph...")
    runner.build_graph()
    write(f"   Graph has {runner.graph.number_of_nodes()} nodes and {runner.graph.number_of_edges()} edges")

    write("\n5. Mapping terminals...")
    runner.map_terminals(max_distance_meters=500)
    write(f"   Mapped {len(runner.terminals)} terminals")

    if len(runner.terminals) >= 2:
        write("\n6. Running algorithms...")

        for algo in ["mst_approximation", "shortest_path_heuristic", "pruned_dijkstra"]:
            try:
                result = runner.run(algorithm=algo)
                write(f"   {algo}: {result.total_weight:.2f}m in {result.execution_time:.4f}s (connected: {result.is_connected})")
            except Exception as e:
                write(f"   {algo}: ERROR - {e}")
    else:
        write("\n   Not enough terminals to run algorithms!")

    write("\n" + "="*60)
    write("TEST COMPLETED SUCCESSFULLY!")
    write("="*60)

except Exception as e:
    import traceback
    write(f"\nERROR: {e}")
    write(traceback.format_exc())

log.close()
print(f"\nLog saved to: {log_file}")
