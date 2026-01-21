import os
import geopandas as gpd
import pandas as pd
import numpy as np
from pathlib import Path

# Configuration
BASE_PATH = "/Users/narekmeloyan/PycharmProjects/Steiner-AI"
LOCATION_PATH = os.path.join(BASE_PATH, "Location Data", "NY", "NY Locations.sqlite")
ROAD_PATH = os.path.join(BASE_PATH, "Road Data", "NY", "Shape")
OUTPUT_PATH = os.path.join(BASE_PATH, "data", "subsets")

# Subset sizes
SUBSET_SIZES = [100, 500, 1000, 5000, 10000]

# Buffer distance for roads (in degrees, ~0.01 ≈ 1km)
ROAD_BUFFER = 0.05


def load_locations():
    """Load locations from SQLite file."""
    print("Loading locations from SQLite...")

    # List layers in the SQLite file
    layers = gpd.list_layers(LOCATION_PATH)
    print(f"  Available layers: {layers}")

    # Load the first layer (or main layer)
    layer_name = layers.iloc[0]['name'] if len(layers) > 0 else None
    print(f"  Loading layer: {layer_name}")

    gdf = gpd.read_file(LOCATION_PATH, layer=layer_name)
    print(f"  Loaded {len(gdf)} locations")
    print(f"  Columns: {gdf.columns.tolist()}")
    print(f"  CRS: {gdf.crs}")

    # Set CRS if not defined (locations have lat/lon, so WGS84)
    if gdf.crs is None:
        print("  CRS not defined, setting to EPSG:4326 (WGS84)")
        gdf = gdf.set_crs("EPSG:4326")

    return gdf


def load_roads():
    """Load and combine road shapefiles."""
    print("\nLoading road data from Shapefiles...")

    # Find road segment shapefiles
    road_files = [
        os.path.join(ROAD_PATH, "Trans_RoadSegment_0.shp"),
        os.path.join(ROAD_PATH, "Trans_RoadSegment_1.shp"),
    ]

    road_gdfs = []
    for road_file in road_files:
        if os.path.exists(road_file):
            print(f"  Loading: {road_file}")
            gdf = gpd.read_file(road_file)
            print(f"    Loaded {len(gdf)} road segments")
            road_gdfs.append(gdf)
        else:
            print(f"  Warning: {road_file} not found")

    if not road_gdfs:
        raise ValueError("No road files found!")

    # Combine all road dataframes
    roads = pd.concat(road_gdfs, ignore_index=True)
    roads = gpd.GeoDataFrame(roads, crs=road_gdfs[0].crs)

    print(f"  Total road segments: {len(roads)}")
    print(f"  Columns: {roads.columns.tolist()}")
    print(f"  CRS: {roads.crs}")

    return roads


def create_clustered_subset(locations_gdf, size, seed=42):
    """Create a spatially clustered subset of locations."""
    np.random.seed(seed)

    if len(locations_gdf) <= size:
        return locations_gdf.copy()

    # Get centroids for clustering
    centroids = locations_gdf.geometry.centroid
    coords = np.array([[geom.x, geom.y] for geom in centroids])

    # Pick a random center point from a dense area
    # Use random sampling to find a good center
    sample_indices = np.random.choice(len(coords), min(100, len(coords)), replace=False)

    # Find the point with most neighbors within a threshold
    best_center_idx = None
    best_neighbor_count = 0
    threshold = 0.1  # degrees

    for idx in sample_indices:
        center = coords[idx]
        distances = np.sqrt(np.sum((coords - center) ** 2, axis=1))
        neighbor_count = np.sum(distances < threshold)
        if neighbor_count > best_neighbor_count:
            best_neighbor_count = neighbor_count
            best_center_idx = idx

    # Select closest points to the best center
    center = coords[best_center_idx]
    distances = np.sqrt(np.sum((coords - center) ** 2, axis=1))
    closest_indices = np.argsort(distances)[:size]

    subset = locations_gdf.iloc[closest_indices].copy()
    return subset


def extract_roads_for_locations(roads_gdf, locations_gdf, buffer=ROAD_BUFFER):
    """Extract roads that intersect with the buffered bounding box of locations."""

    # Get bounding box of locations
    bounds = locations_gdf.total_bounds  # [minx, miny, maxx, maxy]

    # Add buffer
    minx = bounds[0] - buffer
    miny = bounds[1] - buffer
    maxx = bounds[2] + buffer
    maxy = bounds[3] + buffer

    print(f"    Location bounds: [{bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}]")
    print(f"    Buffered bounds: [{minx:.4f}, {miny:.4f}, {maxx:.4f}, {maxy:.4f}]")

    # Ensure CRS match
    if roads_gdf.crs != locations_gdf.crs:
        print(f"    Reprojecting roads from {roads_gdf.crs} to {locations_gdf.crs}")
        roads_gdf = roads_gdf.to_crs(locations_gdf.crs)

    # Filter roads using bounding box
    from shapely.geometry import box
    bbox = box(minx, miny, maxx, maxy)

    # Use spatial index for efficiency
    roads_in_bbox = roads_gdf[roads_gdf.intersects(bbox)].copy()

    return roads_in_bbox


def main():
    print("=" * 60)
    print("Creating Data Subsets for Steiner Network Benchmarking")
    print("=" * 60)

    # Create output directory
    os.makedirs(OUTPUT_PATH, exist_ok=True)

    # Load data
    locations = load_locations()
    roads = load_roads()

    # Create subsets
    for size in SUBSET_SIZES:
        print(f"\n{'=' * 60}")
        print(f"Creating subset of size {size}")
        print("=" * 60)

        # Create subset directory
        subset_dir = os.path.join(OUTPUT_PATH, f"subset_{size}")
        os.makedirs(subset_dir, exist_ok=True)

        # Create location subset (clustered)
        print(f"\n  Selecting {size} clustered locations...")
        subset_locations = create_clustered_subset(locations, size)
        actual_size = len(subset_locations)
        print(f"    Actual locations selected: {actual_size}")

        # Extract roads in the area
        print(f"\n  Extracting roads for the area...")
        subset_roads = extract_roads_for_locations(roads, subset_locations)
        print(f"    Roads extracted: {len(subset_roads)}")

        # Save location subset
        loc_output = os.path.join(subset_dir, "locations.gpkg")
        subset_locations.to_file(loc_output, driver="GPKG")
        print(f"\n  Saved locations to: {loc_output}")

        # Save road subset
        road_output = os.path.join(subset_dir, "roads.gpkg")
        subset_roads.to_file(road_output, driver="GPKG")
        print(f"  Saved roads to: {road_output}")

        # Save metadata
        bounds = subset_locations.total_bounds
        metadata_file = os.path.join(subset_dir, "metadata.txt")
        with open(metadata_file, 'w') as f:
            f.write(f"Subset Size Target: {size}\n")
            f.write(f"Actual Locations: {actual_size}\n")
            f.write(f"Roads Count: {len(subset_roads)}\n")
            f.write(f"Bounding Box:\n")
            f.write(f"  Min X (Lon): {bounds[0]}\n")
            f.write(f"  Min Y (Lat): {bounds[1]}\n")
            f.write(f"  Max X (Lon): {bounds[2]}\n")
            f.write(f"  Max Y (Lat): {bounds[3]}\n")
            f.write(f"CRS: {subset_locations.crs}\n")
        print(f"  Saved metadata to: {metadata_file}")

    print(f"\n{'=' * 60}")
    print(f"All subsets created successfully in: {OUTPUT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
