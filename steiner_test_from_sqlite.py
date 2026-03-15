"""Run Steiner on a location dataset (SpatiaLite) and export the result.

This script:
  1) Reads locations from a SpatiaLite/SQLite file (test1.sqlite)
  2) Builds a road network by querying Postgres via the provided helper
  3) Builds a graph and maps locations to graph terminals
  4) Runs the Steiner solver (pruned_dijkstra)
  5) Exports the solution (edges + nodes) into `outputs/results/`
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import geopandas as gpd

from steiner_aio.components.read_data import output_hadndler
from steiner_aio.components.preprocessing import (

    create_polygon,
    create_linering_from_polygon,
)
from steiner_aio.components.read_data import (
    check_geometry_type,
    put_crs)

from steiner_aio.components.read_data import query_for_road_network

from src.pipeline.runner import SteinerRunner


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_geodataframe(path: Path, layer: Optional[str] = None) -> gpd.GeoDataFrame:
    """Read a vector layer, with fallback layer discovery."""
    try:
        return gpd.read_file(str(path), layer=layer)
    except Exception as exc:
        # Try to auto-detect the layer name (SpatiaLite / GeoPackage)
        try:
            import fiona

            layers = fiona.listlayers(str(path))
            if not layers:
                raise
            return gpd.read_file(str(path), layer=layers[0])
        except Exception:
            raise RuntimeError(f"Unable to read '{path}': {exc}")


def main() -> None:
    project_root = Path(__file__).parent
    outputs_dir = project_root / "outputs"
    results_dir = outputs_dir / "results"
    _ensure_dir(results_dir)

    # -------------------------------------------------------------------------
    # 1) Read locations (from test1.sqlite)
    # -------------------------------------------------------------------------
    location_src = project_root / "data_examples" /"test1"/ "test1 locations.sqlite"
    print(f"Loading locations from: {location_src}")

    locations = _read_geodataframe(location_src)
    print(f"  Loaded {len(locations)} location features")

    locations = check_geometry_type(locations, str(results_dir))
    locations = put_crs(locations, str(results_dir))

    # -------------------------------------------------------------------------
    # 2) Query roads for the location area
    # -------------------------------------------------------------------------
    print("Querying road network for the location area...")
    polygon = create_polygon(locations, buffer_distance=1000)
    line_string_kml = create_linering_from_polygon(polygon)

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
    print(f"  Retrieved {len(roads)} road features")

    
    locations = locations.to_crs("EPSG:4326")
    roads = roads.to_crs("EPSG:4326")

    # -------------------------------------------------------------------------
    # 3) Run Steiner algorithm and export
    # -------------------------------------------------------------------------
    runner = SteinerRunner()
    runner.load_from_geodataframes(roads, locations)
    runner.build_graph()

    runner.map_terminals(max_distance_meters=500)

    result = runner.run(algorithm="pruned_dijkstra")

    print("\n--- Result Summary ---")
    print(f"Terminals: {len(runner.terminals)}")
    print(f"Steiner nodes: {result.node_count}")
    print(f"Steiner edges: {result.edge_count}")
    print(f"Total weight: {result.total_weight:.2f}")
    print(f"Execution time: {result.execution_time:.4f}s")

    print("\nExporting solution to outputs/results...")
    paths = runner.export_solution(result, results_dir, export_format="gpkg")
    for name, path in paths.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
