#!/usr/bin/env python3
"""
Sample runner for steiner_solve.

Usage:
    python example_run.py

    # Or with custom paths:
    python example_run.py --roads roads.gpkg --locations locations.sqlite

    # With export:
    python example_run.py --export outputs/my_run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from steiner_solve import solve


# ---------------------------------------------------------------------------
# Default paths — point at the bundled test data
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
DEFAULT_LOCATIONS = PROJECT_ROOT / "data_examples" / "test1" / "test1 locations.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Steiner solver on road + location data")
    parser.add_argument("--roads", type=str, default=None,
                        help="Path to road network file (.gpkg, .shp, .geojson). "
                             "If omitted, roads are queried from the database.")
    parser.add_argument("--locations", type=str, default=str(DEFAULT_LOCATIONS),
                        help="Path to locations file (.sqlite, .gpkg, .shp)")
    parser.add_argument("--algorithm", type=str, default="pruned_dijkstra",
                        help="Algorithm: pruned_dijkstra, mst_approximation, etc.")
    parser.add_argument("--snap-distance", type=float, default=200.0,
                        help="Max snap distance in meters (default 200)")
    parser.add_argument("--export", type=str, default=None,
                        help="Directory to export solution files")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # If no roads file is provided, query from the database
    # (requires network access to the Azure PostgreSQL instance)
    # ------------------------------------------------------------------
    if args.roads is not None:
        roads = args.roads
    else:
        roads = _query_roads_for_locations(args.locations)

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------
    result = solve(
        roads=roads,
        locations=args.locations,
        algorithm=args.algorithm,
        max_snap_distance_m=args.snap_distance,
        connect_forest=True,
        export_dir=args.export,
    )

    # ------------------------------------------------------------------
    # Print detailed results
    # ------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"  Algorithm:      {result.algorithm}")
    print(f"  Terminals:      {len(result.terminals)}")
    print(f"  Steiner points: {len(result.steiner_points)}")
    print(f"  Total edges:    {result.edge_count}")
    print(f"  Total distance: {result.total_weight_m:,.1f} m  "
          f"({result.total_weight_mi:.2f} mi)")
    print(f"  Connected:      {result.is_connected}")
    print(f"  Time:           {result.execution_time_s:.4f}s")

    if result.edges_gdf is not None and not result.edges_gdf.empty:
        print(f"\n  Solution edges GeoDataFrame: {len(result.edges_gdf)} rows")
        print(f"  Solution nodes GeoDataFrame: {len(result.nodes_gdf)} rows")

    print(f"{'=' * 60}\n")


def _query_roads_for_locations(locations_path: str):
    """
    Query road network from the database for the area around the locations.

    This uses the steiner_aio helpers to build a polygon buffer and call
    the PostgreSQL stored procedure.  Returns a GeoDataFrame in WGS84.
    """
    import geopandas as gpd
    import fiona

    from steiner_aio.components.read_data import (
        check_geometry_type,
        put_crs,
        query_for_road_network,
        output_hadndler,
    )
    from steiner_aio.components.preprocessing import (
        create_polygon,
        create_linering_from_polygon,
    )

    # Load and validate locations
    path = Path(locations_path)
    layer = fiona.listlayers(str(path))[0]
    locations = gpd.read_file(str(path), layer=layer)

    results_dir = Path("outputs/tmp")
    results_dir.mkdir(parents=True, exist_ok=True)

    locations = check_geometry_type(locations, str(results_dir))
    locations = put_crs(locations, str(results_dir))

    # Build query polygon and fetch roads
    polygon = create_polygon(locations, buffer_distance=1000)
    line_string_kml = create_linering_from_polygon(polygon)

    print("Querying road network from database …")
    output = query_for_road_network(
        input=line_string_kml,
        database="wiroidb2",
        user="postgresqlwireless2020",
        password="software2020!!",
        host="wirelesspostgresqlflexible.postgres.database.azure.com",
        port="5432",
        function_name="ww_get_all_roads_in_poly",
        path_for_log=str(results_dir),
    )

    roads = output_hadndler(output)
    roads = roads.to_crs("EPSG:4326")
    print(f"  Retrieved {len(roads)} road segments")
    return roads


if __name__ == "__main__":
    main()
