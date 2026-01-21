#!/usr/bin/env python3
"""
Steiner Network CLI - Command line interface for Steiner tree algorithms.

Usage:
    # Run single algorithm
    python steiner_cli.py run --roads data/roads.gpkg --locations data/locations.gpkg

    # Benchmark all algorithms
    python steiner_cli.py benchmark --subset-dir data/subsets

    # Export results
    python steiner_cli.py run --roads data/roads.gpkg --locations data/locations.gpkg \
        --export ./output --crs ESRI:102008

    # List available algorithms
    python steiner_cli.py list-algorithms
"""

import argparse
import sys
from pathlib import Path


def cmd_run(args):
    """Run a single algorithm on provided data."""
    from src.pipeline import SteinerPipeline, PipelineConfig

    config = PipelineConfig(
        max_snap_distance_meters=args.snap_distance,
        default_crs=args.crs,
        export_format="gpkg" if args.format == "gpkg" else "shp"
    )

    pipeline = SteinerPipeline(config)

    print(f"\n{'=' * 70}")
    print("STEINER NETWORK SOLVER")
    print(f"{'=' * 70}")

    # Load and process
    pipeline.load_data(
        roads_path=args.roads,
        locations_path=args.locations,
        roads_layer=args.roads_layer,
        locations_layer=args.locations_layer
    )
    pipeline.build_graph()
    pipeline.map_terminals()

    # Run algorithm(s)
    if args.algorithm == "all":
        # Exclude slow algorithms by default, unless --include-slow specified
        if hasattr(args, 'include_slow') and args.include_slow:
            results = pipeline.run_all()
        else:
            results = pipeline.run_all(algorithms=SteinerPipeline.fast_algorithms())
    elif "," in args.algorithm:
        # Multiple algorithms specified
        algorithms = [a.strip() for a in args.algorithm.split(",")]
        results = pipeline.run_all(algorithms=algorithms)
    else:
        result = pipeline.run(algorithm=args.algorithm)
        results = {args.algorithm: result}

    # Export if requested
    if args.export:
        pipeline.export_debug(
            results,
            output_dir=args.export,
            crs=args.crs,
            include_full_graph=not args.skip_graph_export
        )

    # Print mileage report
    print("\n" + "=" * 70)
    print("MILEAGE REPORT")
    print("=" * 70)
    mileage = pipeline.get_mileage_report()
    for algo, distances in mileage.items():
        print(f"\n{algo}:")
        print(f"  {distances['meters']:,.2f} meters")
        print(f"  {distances['kilometers']:,.2f} kilometers")
        print(f"  {distances['miles']:,.2f} miles")

    return 0


def cmd_benchmark(args):
    """Run benchmark on multiple subsets."""
    from src.pipeline import Benchmark

    print(f"\n{'=' * 70}")
    print("STEINER NETWORK BENCHMARK")
    print(f"{'=' * 70}")

    benchmark = Benchmark()

    # Load subsets
    if args.subset_dir:
        benchmark.add_subsets_from_directory(args.subset_dir)
    else:
        # Manual subsets
        if args.roads and args.locations:
            benchmark.add_subset("manual", args.roads, args.locations)
        else:
            print("Error: Provide either --subset-dir or --roads/--locations")
            return 1

    if not benchmark.subsets:
        print("Error: No valid subsets found")
        return 1

    # Select algorithms
    algorithms = None
    if args.algorithms:
        algorithms = args.algorithms.split(",")

    # Run benchmark
    if args.export:
        benchmark.run_with_export(
            algorithms=algorithms,
            max_terminals=args.max_terminals,
            export_dir=args.export,
            crs=args.crs
        )
    else:
        benchmark.run(
            algorithms=algorithms,
            max_terminals=args.max_terminals
        )

    # Print summary
    benchmark.print_summary()

    # Save results
    if args.output:
        benchmark.save_results(args.output)

    return 0


def cmd_list_algorithms(args):
    """List available algorithms."""
    from src.algorithms.base import AlgorithmRegistry

    print(f"\n{'=' * 70}")
    print("AVAILABLE ALGORITHMS")
    print(f"{'=' * 70}\n")

    for algo in AlgorithmRegistry.list_algorithms():
        exact = "[EXACT]" if algo['is_exact'] else "[APPROX]"
        print(f"  {algo['name']:<25} {exact}")
        print(f"    {algo['description']}")
        print(f"    Complexity: {algo['complexity']}")
        print()

    return 0


def cmd_info(args):
    """Show information about a dataset."""
    import geopandas as gpd

    print(f"\n{'=' * 70}")
    print("DATASET INFORMATION")
    print(f"{'=' * 70}\n")

    if args.roads:
        roads = gpd.read_file(args.roads, layer=args.roads_layer)
        print(f"Roads: {args.roads}")
        print(f"  Segments: {len(roads)}")
        print(f"  CRS: {roads.crs}")
        print(f"  Bounds: {roads.total_bounds}")
        print()

    if args.locations:
        locs = gpd.read_file(args.locations, layer=args.locations_layer)
        print(f"Locations: {args.locations}")
        print(f"  Points: {len(locs)}")
        print(f"  CRS: {locs.crs}")
        print(f"  Bounds: {locs.total_bounds}")
        print()

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Steiner Network Solver - Find optimal road networks connecting locations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick run with default algorithm
  python steiner_cli.py run -r roads.gpkg -l locations.gpkg

  # Run specific algorithm with export
  python steiner_cli.py run -r roads.gpkg -l locations.gpkg -a mst_approximation -e ./output

  # Benchmark all algorithms on subsets
  python steiner_cli.py benchmark --subset-dir data/subsets -e ./benchmark_output

  # List available algorithms
  python steiner_cli.py list-algorithms
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run Steiner algorithm")
    run_parser.add_argument("-r", "--roads", required=True, help="Path to road network file")
    run_parser.add_argument("-l", "--locations", required=True, help="Path to locations file")
    run_parser.add_argument("-a", "--algorithm", default="mst_approximation",
                           help="Algorithm to use (or 'all' for benchmark)")
    run_parser.add_argument("-e", "--export", help="Export results to directory")
    run_parser.add_argument("--crs", default="EPSG:4326",
                           help="Output CRS (EPSG:4326 or ESRI:102008)")
    run_parser.add_argument("--format", choices=["shp", "gpkg"], default="shp",
                           help="Export format")
    run_parser.add_argument("--snap-distance", type=float, default=100.0,
                           help="Maximum snap distance in meters")
    run_parser.add_argument("--roads-layer", help="Layer name for roads (geopackage)")
    run_parser.add_argument("--locations-layer", help="Layer name for locations (geopackage)")
    run_parser.add_argument("--skip-graph-export", action="store_true",
                           help="Skip exporting full graph (faster for large networks)")
    run_parser.add_argument("--include-slow", action="store_true",
                           help="Include slow algorithms (genetic, shortest_path_heuristic) when using -a all")
    run_parser.set_defaults(func=cmd_run)

    # Benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark multiple algorithms")
    bench_parser.add_argument("--subset-dir", help="Directory containing subsets")
    bench_parser.add_argument("-r", "--roads", help="Path to road network file")
    bench_parser.add_argument("-l", "--locations", help="Path to locations file")
    bench_parser.add_argument("--algorithms", help="Comma-separated list of algorithms")
    bench_parser.add_argument("-e", "--export", help="Export results to directory")
    bench_parser.add_argument("-o", "--output", help="Save results JSON to file")
    bench_parser.add_argument("--crs", default="EPSG:4326",
                             help="Output CRS (EPSG:4326 or ESRI:102008)")
    bench_parser.add_argument("--max-terminals", type=int, help="Limit terminal count")
    bench_parser.set_defaults(func=cmd_benchmark)

    # List algorithms command
    list_parser = subparsers.add_parser("list-algorithms", help="List available algorithms")
    list_parser.set_defaults(func=cmd_list_algorithms)

    # Info command
    info_parser = subparsers.add_parser("info", help="Show dataset information")
    info_parser.add_argument("-r", "--roads", help="Path to road network file")
    info_parser.add_argument("-l", "--locations", help="Path to locations file")
    info_parser.add_argument("--roads-layer", help="Layer name for roads")
    info_parser.add_argument("--locations-layer", help="Layer name for locations")
    info_parser.set_defaults(func=cmd_info)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
