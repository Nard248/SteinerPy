from azure.storage.blob import BlobServiceClient
import pandas as pd
import io
import geopandas as gpd
import networkx as nx
from pathlib import Path
from shapely.geometry import Point
from src.pipeline.runner import SteinerRunner
from steiner_aio.components.read_data import put_crs

ACCOUNT_NAME = "webviewerstorage"
CONTAINER_NAME = "state-road-graphs"
STAT_TOKEN = "sp=r&st=2026-03-13T19:15:37Z&se=2026-03-14T03:30:37Z&spr=https&sv=2024-11-04&sr=c&sig=Qb6uTnmcF%2BS1KqzLKGDNX5VtUakaR9983axwsl35Dbg%3D"
client = BlobServiceClient(account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
                            credential=STAT_TOKEN)

container = client.get_container_client(CONTAINER_NAME)

def read_blob_to_dataframe(blob_name):
    blob_client = container.get_blob_client(blob_name)
    blob_data = blob_client.download_blob().readall()
    df = pd.read_parquet(io.BytesIO(blob_data))
    return df

# Read nodes and edges from Azure Blob
nodes_df = read_blob_to_dataframe("nodes_NY.parquet")
edges_df = read_blob_to_dataframe("edges_NY.parquet")

print(f"Loaded {len(nodes_df)} nodes and {len(edges_df)} edges from blob.")

# Read locations from data_examples
data_dir = Path(__file__).parent / "data_examples"
locations_path = data_dir / "Albany OLT-01 UG Locations.sqlite"

locations = gpd.read_file(str(locations_path))
print(f"Loaded {len(locations)} locations.")

# Assume locations are in EPSG:4326, convert to projected if needed
# if locations.crs != "EPSG:4326":
#     locations = locations.to_crs("EPSG:4326")

# locations = locations.to_crs("EPSG:4326")
# locations = put_crs(locations,"")
# Create a buffer around locations (e.g., 1 km)
buffer_distance = 1000  # meters
locations = locations.set_crs("EPSG:4326")
locations_projected = locations.to_crs("ESRI:102008")  # Web Mercator for buffering
buffered = locations_projected.buffer(buffer_distance)
buffered_union = buffered.unary_union

# Filter nodes within the buffer
nodes_gdf = gpd.GeoDataFrame(nodes_df, geometry=[Point(xy) for xy in zip(nodes_df.x, nodes_df.y)], crs="ESRI:102008")
#nodes_projected = nodes_gdf.to_crs("EPSG:3857")
nodes_filtered = nodes_gdf[nodes_gdf.geometry.within(buffered_union)]

nodes_filtered = nodes_filtered.to_crs("EPSG:4326")

print(f"Filtered to {len(nodes_filtered)} nodes within buffer.")

# Filter edges where both nodes are in filtered nodes
node_ids = set(nodes_filtered.node_id)
edges_filtered = edges_df[edges_df['source'].isin(node_ids) & edges_df['target'].isin(node_ids)]

print(f"Filtered to {len(edges_filtered)} edges.")

# nodes_filtered = nodes_filtered.to_crs("EPSG:4326")
nodes_filtered['x'] = nodes_filtered.geometry.x
nodes_filtered['y'] = nodes_filtered.geometry.y
# Build the graph
graph = nx.Graph()
for _, row in nodes_filtered.iterrows():
    graph.add_node(row['node_id'], x=row['x'], y=row['y'])

for _, row in edges_filtered.iterrows():
    graph.add_edge(row['source'], row['target'], weight=row['weight'])

print(f"Built graph with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges.")

# Run Steiner
runner = SteinerRunner()
runner._graph = graph
runner._locations = locations

runner.map_terminals(max_distance_meters=500)

result = runner.run(algorithm="pruned_dijkstra")

print("\n--- Result Summary ---")
print(f"Terminals: {len(runner.terminals)}")
print(f"Steiner nodes: {result.node_count}")
print(f"Steiner edges: {result.edge_count}")
print(f"Total weight: {result.total_weight:.2f}")
print(f"Execution time: {result.execution_time:.4f}s")

# Export
outputs_dir = Path(__file__).parent / "outputs"
outputs_dir.mkdir(exist_ok=True)
paths = runner.export_solution(result, outputs_dir, export_format="gpkg")
for name, path in paths.items():
    print(f"Exported {name}: {path}")
