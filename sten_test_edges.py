import pandas as pd
import geopandas as gpd
import networkx as nx
from pathlib import Path
from shapely.geometry import Point, LineString
from src.pipeline.runner import SteinerRunner
import shapely
import numpy as np


def connect_forest(steiner_graph: nx.Graph, full_graph: nx.Graph) -> nx.Graph:
    """Connect a Steiner forest into a single tree.

    For each disconnected component, finds the shortest path back to the
    already-connected main body using multi-source Dijkstra on the full graph,
    then adds those edges to the result.
    """
    result = steiner_graph.copy()

    while True:
        components = list(nx.connected_components(result))
        if len(components) == 1:
            break

        # Largest component becomes the root; grow it each iteration
        components.sort(key=len, reverse=True)
        main_nodes = components[0]

        # Single multi-source Dijkstra from the entire main component
        dist, paths = nx.multi_source_dijkstra(full_graph, main_nodes, weight='weight')

        # Find the cheapest entry point into any other component
        best_cost = float('inf')
        best_path = None
        for comp in components[1:]:
            for node in comp:
                if node in dist and dist[node] < best_cost:
                    best_cost = dist[node]
                    best_path = paths[node]

        if best_path is None or len(best_path) < 2:
            print("  Warning: some components cannot be reached — graph has true gaps.")
            break

        # Stitch the path into the result graph
        for u, v in zip(best_path[:-1], best_path[1:]):
            if full_graph.has_edge(u, v):
                result.add_edge(u, v, **full_graph[u][v])
                for n in (u, v):
                    for attr in ('x', 'y'):
                        if attr in full_graph.nodes[n]:
                            result.nodes[n][attr] = full_graph.nodes[n][attr]

    return result


def split_edges(gdf: gpd.GeoDataFrame, segment_length: float) -> gpd.GeoDataFrame:
    """Split each LineString in gdf into sub-segments of at most `segment_length` (in CRS units).

    Args:
        gdf: GeoDataFrame of LineString edges.
        segment_length: Maximum length of each output segment (same units as gdf CRS).

    Returns:
        New GeoDataFrame with split segments; non-geometry columns are inherited from the parent row.
    """
    rows = []
    for _, row in gdf.iterrows():
        line = row.geometry
        total = line.length
        if total <= segment_length:
            rows.append(row)
            continue
        n_segments = int(np.ceil(total / segment_length))
        distances = np.linspace(0, total, n_segments + 1)
        points = [line.interpolate(d) for d in distances]
        for start_pt, end_pt in zip(points[:-1], points[1:]):
            new_row = row.copy()
            new_row.geometry = LineString([start_pt, end_pt])
            new_row['length'] = new_row.geometry.length
            rows.append(new_row)
    return gpd.GeoDataFrame(rows, crs=gdf.crs).reset_index(drop=True)


# Read edges
edges_df = pd.read_parquet("edges_NY.parquet")
edges_df['geometry'] = edges_df['geometry'].apply(lambda x: shapely.from_wkb(x))

# Make a GeoDataFrame — coordinates are in ESRI:102008
edges_gdf = gpd.GeoDataFrame(edges_df, geometry='geometry', crs="ESRI:102008")

print(f"Loaded {len(edges_gdf)} edges.")

# Read locations and build buffer
data_dir = Path(__file__).parent / "data_examples"

for i in range(1, 4):

    locations_path = data_dir / f"test{i}" / f"test{i} locations.sqlite"
    locations = gpd.read_file(str(locations_path))
    locations = locations.set_crs("EPSG:4326")
    print(f"Loaded {len(locations)} locations.")

    buffer_distance = 1000  # meters
    locations_projected = locations.to_crs("ESRI:102008")
    buffered_union = locations_projected.buffer(buffer_distance).union_all()

    # Spatially filter edges that intersect the buffer
    edges_filtered = edges_gdf[edges_gdf.geometry.intersects(buffered_union)].copy()
    print(f"Filtered to {len(edges_filtered)} edges within buffer.")
    edges_filtered.to_file(f"outputs/test{i}_edges_filtered.geojson", driver="GeoJSON")  # For debugging

    edges_filtered = edges_filtered.reset_index(drop=True)

    # Split long segments into ~50 m chunks (units: ESRI:102008 = meters)
    edges_filtered = split_edges(edges_filtered, segment_length=50)
    print(f"After splitting: {len(edges_filtered)} segments.")

    # # Run Steiner
    edges_filtered = edges_filtered.to_crs("EPSG:4326")
    runner = SteinerRunner()
    runner.load_from_geodataframes( edges_filtered,locations)
    runner.build_graph()
    # runner._graph = graph
    # runner._locations = locations

    runner.map_terminals(max_distance_meters=500)

    result = runner.run(algorithm="pruned_dijkstra")

    # Connect forest into a single tree if needed
    if not result.is_connected:
        print("  Forest detected — connecting components...")
        result.steiner_graph = connect_forest(result.steiner_graph, runner._graph)
        result.node_count = result.steiner_graph.number_of_nodes()
        result.edge_count = result.steiner_graph.number_of_edges()
        result.total_weight = sum(d.get('weight', 0) for _, _, d in result.steiner_graph.edges(data=True))
        result.is_connected = nx.is_connected(result.steiner_graph)
        print(f"  Connected: {result.is_connected}")

    print("\n--- Result Summary ---")
    print(f"Terminals: {len(runner.terminals)}")
    print(f"Steiner nodes: {result.node_count}")
    print(f"Steiner edges: {result.edge_count}")
    print(f"Total weight: {result.total_weight:.2f}")
    print(f"Execution time: {result.execution_time:.4f}s")

    # Export
    outputs_dir = Path(__file__).parent / "outputs"
    outputs_dir.mkdir(exist_ok=True)
    paths = runner.export_solution(result, outputs_dir, export_format="gpkg",
                                   filename_prefix=f"test{i}")
    for name, path in paths.items():
        print(f"Exported {name}: {path}")
