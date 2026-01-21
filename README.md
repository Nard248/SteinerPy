# Steiner Network Framework

A Python framework for solving the **Steiner Tree Problem** on road networks. Given a set of locations (terminals) and a road network, this framework finds the shortest subgraph that connects all locations.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Algorithms](#algorithms)
- [Input Data Formats](#input-data-formats)
- [Output Files](#output-files)
- [CLI Reference](#cli-reference)
- [Python API](#python-api)
- [Architecture](#architecture)
- [Developer Guide](#developer-guide)

---

## Overview

### The Steiner Tree Problem

The **Steiner Tree Problem** asks: given a graph and a subset of vertices called *terminals*, find the minimum-weight tree that connects all terminals. This tree may include additional vertices called *Steiner points* that help reduce the total weight.

**Real-world application**: Finding the optimal road network to connect a set of locations (e.g., warehouses, delivery points, facilities) while minimizing total road distance.

### What This Framework Does

```
Input:                          Output:
┌─────────────────────┐        ┌─────────────────────┐
│  Road Network       │        │  Optimal Subgraph   │
│  (LineStrings)      │        │  (Steiner Tree)     │
│         +           │  ───►  │                     │
│  Locations          │        │  + Mileage Report   │
│  (Points)           │        │  + Debug Shapefiles │
└─────────────────────┘        └─────────────────────┘
```

---

## Installation

### Requirements

- Python 3.9+
- GDAL/OGR (for geospatial operations)

### Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies:**
- `geopandas` - Geospatial data handling
- `networkx` - Graph algorithms
- `shapely` - Geometric operations
- `scipy` - Spatial indexing (KD-tree)
- `pyproj` - Coordinate transformations
- `rtree` - R-tree spatial index
- `fiona` - File I/O for shapefiles

---

## Quick Start

### CLI Usage

```bash
# Run a single algorithm
python steiner_cli.py run \
    -r data/subsets/subset_100/roads.gpkg \
    -l data/subsets/subset_100/locations.gpkg \
    -a mst_approximation \
    -e output/results \
    --crs ESRI:102008

# Benchmark multiple algorithms
python steiner_cli.py benchmark \
    --subset-dir data/subsets \
    --algorithms mst_approximation,pruned_dijkstra,mst_steiner_points \
    -e output/benchmark \
    --crs ESRI:102008

# List available algorithms
python steiner_cli.py list-algorithms
```

### Python API

```python
from src.pipeline import SteinerPipeline

# Create pipeline and run
pipeline = SteinerPipeline()
pipeline.load_data("roads.gpkg", "locations.gpkg")
pipeline.build_graph()
pipeline.map_terminals(max_distance_meters=100.0)

# Run single algorithm
result = pipeline.run("mst_approximation")

# Or benchmark all fast algorithms
results = pipeline.run_all(algorithms=SteinerPipeline.fast_algorithms())

# Export results
pipeline.export_debug(results, output_dir="./output", crs="ESRI:102008")
```

---

## Core Concepts

### 1. Graph Construction

The framework converts road network geometries into a graph structure:

```
Road Network (GeoDataFrame)          Graph (NetworkX)
┌────────────────────────┐          ┌────────────────────────┐
│  LineString features   │          │  Nodes: Intersections  │
│  with coordinates      │   ───►   │  Edges: Road segments  │
│                        │          │  Weights: Distance (m) │
└────────────────────────┘          └────────────────────────┘
```

**Process:**
1. Extract all LineString geometries from road data
2. Identify vertices: endpoints + intersection points
3. Apply snapping tolerance (default 1.0m) to merge nearby nodes
4. Create edges between consecutive vertices along each road
5. Calculate edge weights using geodesic distance (WGS84 ellipsoid)

### 2. Terminals

**Terminals** are the nodes that MUST be connected by the solution. They are created by "snapping" location points to the nearest graph node.

```
Locations (Points)              Terminals (Graph Nodes)
     ●                               ○───────○
      \                              │       │
       ● ──────────────────►         ●───────●  (snapped to road)
      /                              │       │
     ●                               ○───────○
```

**Snapping process:**
1. Build KD-tree from all graph node coordinates
2. For each location point, find nearest graph node
3. If distance ≤ max_snap_distance, map location → node
4. Deduplicate: multiple locations may snap to same node

### 3. Steiner Points

**Steiner points** are non-terminal nodes included in the solution to reduce total distance. They are junction points that help connect terminals more efficiently.

```
Without Steiner point:          With Steiner point:
    A─────────────B                 A───────S───────B
    │             │                         │
    │             │                         │
    C─────────────D                 C───────┘

Total: Long paths                Total: Shorter via junction S
```

### 4. Solution (Steiner Tree)

The output is a **tree** (connected graph with no cycles) that:
- Includes all terminal nodes
- May include additional Steiner points
- Has minimum total edge weight (distance)

---

## Algorithms

### Overview

| Algorithm | Type | Speed | Best For |
|-----------|------|-------|----------|
| `mst_approximation` | 2-approx | Fast | General use, good balance |
| `pruned_dijkstra` | Heuristic | Fastest | Large networks, many terminals |
| `dijkstra_steiner` | Exact/Fallback | Medium | Small terminal sets (≤12) |
| `mst_steiner_points` | Heuristic | Medium | Road networks with junctions |
| `shortest_path_heuristic` | Greedy | Slow | Small instances only |
| `genetic` | Metaheuristic | Slowest | Exploration, possibly better solutions |

### Detailed Descriptions

#### 1. MST Approximation (`mst_approximation`)

**Type:** 2-approximation algorithm
**Complexity:** O(|T|² × |V| log |V|)
**Guarantee:** Solution ≤ 2 × optimal

**Algorithm:**
```
1. Compute shortest paths between all terminal pairs
2. Build "metric closure" graph:
   - Nodes: terminals only
   - Edge weights: shortest path distances
3. Find MST of metric closure
4. Replace metric edges with actual shortest paths
5. Remove redundant edges (prune non-terminal leaves)
```

**When to use:** Default choice for most cases. Provides theoretical guarantee.

---

#### 2. Pruned Dijkstra (`pruned_dijkstra`)

**Type:** Multi-source Dijkstra heuristic
**Complexity:** O(|V| log |V| + |E|)
**Guarantee:** None (but often near-optimal)

**Algorithm:**
```
1. Initialize priority queue with all terminals (distance=0)
2. Run Dijkstra, tracking which terminal "owns" each node
3. When frontiers from different terminals meet:
   - Record the meeting edge as potential connection
4. Build MST from connection edges using Union-Find
5. Reconstruct paths and prune unnecessary branches
```

**When to use:** Large graphs, many terminals. Fastest algorithm.

---

#### 3. Dijkstra-Steiner DP (`dijkstra_steiner`)

**Type:** Dynamic programming (exact for small instances)
**Complexity:** O(3^|T| × |V|) - exponential in terminals
**Guarantee:** Optimal for |T| ≤ 12

**Algorithm:**
```
1. Use bitmask DP: dp[mask][v] = min cost to connect terminals in mask at vertex v
2. Base case: dp[{t}][t] = 0 for each terminal t
3. Transitions:
   a. Merge: dp[S][v] = min(dp[S₁][v] + dp[S₂][v]) for S = S₁ ∪ S₂
   b. Extend: dp[S][u] = min(dp[S][v] + weight(v,u))
4. Answer: min over all v of dp[all_terminals][v]
5. Backtrack to reconstruct solution
```

**When to use:** When you need optimal solution and have ≤12 terminals.

**Note:** Falls back to `shortest_path_heuristic` for >12 terminals.

---

#### 4. MST with Steiner Points (`mst_steiner_points`)

**Type:** Enhanced MST heuristic
**Complexity:** O(|T| × |V| log |V| + |V|²)
**Guarantee:** None

**Algorithm:**
```
1. Identify candidate Steiner points:
   - High-degree nodes (road junctions)
   - Score by: degree × terminals_reachable / avg_distance
2. Add top-k candidates to terminal set
3. Apply MST approximation on extended set
4. Prune leaves iteratively
```

**When to use:** Road networks where junctions matter.

---

#### 5. Shortest Path Heuristic (`shortest_path_heuristic`)

**Type:** Greedy approximation
**Complexity:** O(|T|² × |V| log |V|)
**Guarantee:** None

**Algorithm:**
```
1. Start with arbitrary terminal as root
2. Repeat until all terminals connected:
   a. Find nearest unconnected terminal to current tree
   b. Add shortest path to tree
3. Return resulting tree
```

**When to use:** Small instances. Simple but often suboptimal.

**Warning:** Slow on large instances - excluded from fast algorithms.

---

#### 6. Genetic Algorithm (`genetic`)

**Type:** Metaheuristic
**Complexity:** O(generations × population × |V| log |V|)
**Guarantee:** None

**Algorithm:**
```
1. Initialize population: random subsets of potential Steiner points
2. For each generation:
   a. Evaluate fitness = -total_weight (minimize)
   b. Selection: tournament selection
   c. Crossover: union/intersection of parent sets
   d. Mutation: add/remove random nodes
3. Early stopping after 20 generations without improvement
4. Return best individual
```

**When to use:** When you want to explore solution space more thoroughly.

**Warning:** Slow - excluded from fast algorithms.

---

## Input Data Formats

### Road Network File

**Supported formats:** GeoPackage (.gpkg), Shapefile (.shp), GeoJSON

**Required:**
- Geometry column with `LineString` or `MultiLineString` features
- CRS defined (preferably EPSG:4326 / WGS84)

**Example structure:**
```
┌─────────┬──────────────────────────────────┬───────────┐
│ FID     │ geometry                         │ road_name │
├─────────┼──────────────────────────────────┼───────────┤
│ 1       │ LINESTRING(-73.9 40.7, -73.8 40.8)│ Main St   │
│ 2       │ LINESTRING(-73.8 40.8, -73.7 40.9)│ Oak Ave   │
└─────────┴──────────────────────────────────┴───────────┘
```

### Locations File

**Supported formats:** GeoPackage (.gpkg), Shapefile (.shp), GeoJSON, SQLite

**Required:**
- Geometry column with `Point` features
- CRS defined (will be reprojected to match roads if different)

**Example structure:**
```
┌─────────┬─────────────────────────┬──────────────┐
│ FID     │ geometry                │ name         │
├─────────┼─────────────────────────┼──────────────┤
│ 1       │ POINT(-73.85 40.75)     │ Warehouse A  │
│ 2       │ POINT(-73.82 40.78)     │ Store B      │
└─────────┴─────────────────────────┴──────────────┘
```

---

## Output Files

### Directory Structure

```
output/
├── graph_nodes.shp          # All road network nodes
├── graph_edges.shp          # Full road network edges
├── terminals.shp            # Snapped terminal points
├── solution_<algo>_edges.shp    # Solution edges per algorithm
├── solution_<algo>_nodes.shp    # Solution nodes per algorithm
└── mileage_summary.csv      # Distance statistics
```

### File Descriptions

#### `graph_nodes.shp` - Road Network Nodes

All vertices in the constructed graph.

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | Integer | Unique node identifier |
| `x` | Float | Longitude (WGS84) |
| `y` | Float | Latitude (WGS84) |
| `degree` | Integer | Number of connected edges |
| `is_termina` | Boolean | Whether this is a terminal node |
| `node_type` | String | 'terminal', 'junction', or 'intermediate' |

#### `graph_edges.shp` - Road Network Edges

All edges in the constructed graph.

| Field | Type | Description |
|-------|------|-------------|
| `from_node` | Integer | Source node ID |
| `to_node` | Integer | Target node ID |
| `weight_m` | Float | Edge length in meters |
| `weight_km` | Float | Edge length in kilometers |
| `weight_mi` | Float | Edge length in miles |

#### `terminals.shp` - Terminal (Snap) Points

Location points snapped to the road network.

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | Integer | Graph node ID this location snapped to |
| `x` | Float | Longitude |
| `y` | Float | Latitude |
| `degree` | Integer | Node degree in graph |
| `loc_count` | Integer | Number of locations snapped to this node |

#### `solution_<algo>_edges.shp` - Solution Edges

Edges in the Steiner tree solution for each algorithm.

| Field | Type | Description |
|-------|------|-------------|
| `from_node` | Integer | Source node ID |
| `to_node` | Integer | Target node ID |
| `weight_m` | Float | Edge length in meters |
| `weight_km` | Float | Edge length in kilometers |
| `weight_mi` | Float | Edge length in miles |
| `edge_type` | String | 'terminal-terminal', 'terminal-steiner', 'steiner-steiner' |
| `algorithm` | String | Algorithm name |

#### `solution_<algo>_nodes.shp` - Solution Nodes

Nodes in the Steiner tree solution for each algorithm.

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | Integer | Node ID |
| `x` | Float | Longitude |
| `y` | Float | Latitude |
| `degree` | Integer | Degree in solution graph |
| `is_termina` | Boolean | True if terminal |
| `is_steiner` | Boolean | True if Steiner point |
| `node_type` | String | 'terminal' or 'steiner' |
| `algorithm` | String | Algorithm name |

#### `mileage_summary.csv` - Distance Statistics

Summary of all algorithm results.

| Column | Description |
|--------|-------------|
| `algorithm` | Algorithm name |
| `total_meters` | Total solution distance in meters |
| `total_kilometers` | Total distance in km |
| `total_miles` | Total distance in miles |
| `total_feet` | Total distance in feet |
| `node_count` | Number of nodes in solution |
| `edge_count` | Number of edges in solution |
| `terminal_count` | Number of terminals |
| `steiner_point_count` | Number of Steiner points |
| `is_connected` | Whether solution connects all terminals |
| `execution_time_sec` | Algorithm runtime in seconds |

---

## CLI Reference

### `run` - Run Algorithm(s)

```bash
python steiner_cli.py run [OPTIONS]
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `-r, --roads` | Yes | - | Path to road network file |
| `-l, --locations` | Yes | - | Path to locations file |
| `-a, --algorithm` | No | `mst_approximation` | Algorithm name, 'all', or comma-separated list |
| `-e, --export` | No | - | Export directory |
| `--crs` | No | `EPSG:4326` | Output CRS (`EPSG:4326` or `ESRI:102008`) |
| `--format` | No | `shp` | Export format (`shp` or `gpkg`) |
| `--snap-distance` | No | `100.0` | Max snap distance in meters |
| `--skip-graph-export` | No | False | Skip full graph export |
| `--include-slow` | No | False | Include slow algorithms with `-a all` |

### `benchmark` - Benchmark Multiple Datasets

```bash
python steiner_cli.py benchmark [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--subset-dir` | Directory containing subset folders |
| `-r, --roads` | Single roads file (alternative to subset-dir) |
| `-l, --locations` | Single locations file |
| `--algorithms` | Comma-separated algorithm list |
| `-e, --export` | Export directory |
| `-o, --output` | Save results JSON to file |
| `--crs` | Output CRS |
| `--max-terminals` | Limit terminal count |

### `list-algorithms` - Show Available Algorithms

```bash
python steiner_cli.py list-algorithms
```

### `info` - Show Dataset Information

```bash
python steiner_cli.py info -r roads.gpkg -l locations.gpkg
```

---

## Python API

### SteinerPipeline

The main interface for running Steiner algorithms.

```python
from src.pipeline import SteinerPipeline, PipelineConfig

# Configure pipeline
config = PipelineConfig(
    coord_precision=6,              # Decimal places for coordinates
    snap_tolerance_meters=1.0,      # Merge nodes within this distance
    max_snap_distance_meters=100.0, # Max location-to-road distance
    default_algorithm="mst_approximation",
    default_crs="EPSG:4326",
    export_format="shp"
)

pipeline = SteinerPipeline(config)
```

#### Stage 1: Load Data

```python
# From files
pipeline.load_data(
    roads_path="roads.gpkg",
    locations_path="locations.gpkg",
    roads_layer=None,      # Optional layer name for geopackage
    locations_layer=None
)

# From GeoDataFrames
pipeline.load_from_geodataframes(roads_gdf, locations_gdf)
```

#### Stage 2: Build Graph

```python
pipeline.build_graph()

# Access graph
graph = pipeline.graph  # NetworkX Graph
print(f"Nodes: {graph.number_of_nodes()}")
print(f"Edges: {graph.number_of_edges()}")
```

#### Stage 3: Map Terminals

```python
pipeline.map_terminals(max_distance_meters=100.0)

# Access terminals
terminals = pipeline.terminals  # Set[int] of node IDs

# Or set terminals manually
pipeline.set_terminals({1, 5, 10, 15})
```

#### Stage 4: Run Algorithms

```python
# Single algorithm
result = pipeline.run("mst_approximation")

# Multiple algorithms
results = pipeline.run_all(algorithms=[
    "mst_approximation",
    "pruned_dijkstra"
])

# Fast algorithms only (excludes genetic, shortest_path_heuristic)
results = pipeline.run_all(algorithms=SteinerPipeline.fast_algorithms())

# Exclude specific algorithms
results = pipeline.run_all(
    algorithms=SteinerPipeline.exclude_algorithms(["genetic"])
)
```

#### Stage 5: Export Results

```python
# Full debug package
paths = pipeline.export_debug(
    results,
    output_dir="./output",
    crs="ESRI:102008",
    export_format="shp",
    include_full_graph=True
)

# Single solution
paths = pipeline.export_solution(result, "./output", crs="EPSG:4326")

# Get mileage report
mileage = pipeline.get_mileage_report()
for algo, distances in mileage.items():
    print(f"{algo}: {distances['kilometers']:.2f} km")
```

### AlgorithmResult

Result object returned by algorithms.

```python
result = pipeline.run("mst_approximation")

# Properties
result.steiner_graph      # NetworkX Graph of solution
result.terminals          # Set[int] of terminal node IDs
result.steiner_points     # Set[int] of Steiner point node IDs
result.total_weight       # Total edge weight in meters
result.node_count         # Number of nodes in solution
result.edge_count         # Number of edges in solution
result.is_connected       # True if all terminals connected
result.execution_time     # Runtime in seconds
result.algorithm_name     # Name of algorithm used
result.metadata           # Dict with algorithm-specific data
```

### Direct Algorithm Usage

```python
from src.algorithms import AlgorithmRegistry

# List algorithms
for info in AlgorithmRegistry.list_algorithms():
    print(f"{info['name']}: {info['description']}")

# Create and run algorithm directly
algo = AlgorithmRegistry.create("mst_approximation")
result = algo.solve(graph, terminals)
```

---

## Architecture

### Project Structure

```
Steiner-AI/
├── src/
│   ├── algorithms/           # Algorithm implementations
│   │   ├── base.py          # Base class + registry
│   │   ├── mst_based.py     # MST algorithms
│   │   ├── shortest_path.py # Path-based algorithms
│   │   ├── pruned_dijkstra.py
│   │   └── genetic.py
│   │
│   ├── data/                 # Data processing
│   │   ├── graph_builder.py # Road → Graph conversion
│   │   ├── spatial_index.py # R-tree queries
│   │   └── loader.py        # GIS data loading
│   │
│   └── pipeline/             # Main interface
│       ├── pipeline.py      # SteinerPipeline class
│       ├── runner.py        # Legacy runner
│       ├── benchmark.py     # Benchmarking
│       └── exporter.py      # Shapefile export
│
├── data/subsets/             # Test datasets
├── steiner_cli.py            # CLI entry point
└── requirements.txt
```

### Class Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     SteinerPipeline                         │
├─────────────────────────────────────────────────────────────┤
│ - config: PipelineConfig                                    │
│ - _state: PipelineState                                     │
│ - _results: Dict[str, AlgorithmResult]                      │
├─────────────────────────────────────────────────────────────┤
│ + load_data(roads, locations)                               │
│ + build_graph() → builds via GraphBuilder                   │
│ + map_terminals(max_distance)                               │
│ + run(algorithm) → uses AlgorithmRegistry                   │
│ + run_all(algorithms)                                       │
│ + export_debug(results, output_dir) → uses SteinerExporter  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AlgorithmRegistry                        │
├─────────────────────────────────────────────────────────────┤
│ + register(cls) → decorator                                 │
│ + create(name, **params) → SteinerAlgorithm                 │
│ + available_names() → List[str]                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                SteinerAlgorithm (Abstract)                  │
├─────────────────────────────────────────────────────────────┤
│ + name, description, complexity, is_exact                   │
│ + solve(graph, terminals) → AlgorithmResult                 │
│ # _validate_inputs()                                        │
│ # _extract_subgraph()                                       │
│ # _compute_total_weight()                                   │
│ # _check_connectivity()                                     │
└─────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
┌────────┴────────┐ ┌────────┴────────┐ ┌────────┴────────┐
│ MSTApproximation│ │ PrunedDijkstra  │ │ GeneticSteiner  │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## Developer Guide

### Adding a New Algorithm

1. Create class in `src/algorithms/`:

```python
# src/algorithms/my_algorithm.py
from .base import SteinerAlgorithm, AlgorithmResult, AlgorithmRegistry

@AlgorithmRegistry.register
class MyAlgorithm(SteinerAlgorithm):
    """Description of your algorithm."""

    name = "my_algorithm"
    description = "Brief description"
    complexity = "O(...)"
    is_exact = False  # True if algorithm guarantees optimal

    def __init__(self, my_param: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self.my_param = my_param

    def solve(self, graph, terminals, **kwargs):
        start_time = time.perf_counter()
        self._validate_inputs(graph, terminals)

        # Your algorithm here
        edges = []  # List of (u, v) tuples

        # Build result
        steiner_graph = self._extract_subgraph(graph, edges)

        return AlgorithmResult(
            steiner_graph=steiner_graph,
            terminals=terminals,
            steiner_points=set(steiner_graph.nodes()) - terminals,
            total_weight=self._compute_total_weight(steiner_graph),
            execution_time=time.perf_counter() - start_time,
            algorithm_name=self.name,
            is_connected=self._check_connectivity(steiner_graph, terminals)
        )
```

2. Import in `src/algorithms/__init__.py`:

```python
from .my_algorithm import MyAlgorithm
```

3. Algorithm is now automatically available via registry.

### Extending the Exporter

Add new export methods to `src/pipeline/exporter.py`:

```python
def export_custom_layer(self, data, filename):
    """Export custom data layer."""
    gdf = gpd.GeoDataFrame(data, crs=CRS_WGS84)
    return self._save_gdf(gdf, filename)
```

### Graph Structure Details

The graph uses NetworkX with this structure:

```python
# Node attributes
graph.nodes[node_id] = {
    'x': float,      # Longitude
    'y': float,      # Latitude
}

# Edge attributes
graph[u][v] = {
    'weight': float,           # Distance in meters (geodesic)
    'geometry': LineString,    # Original road geometry
}
```

### Distance Calculation

Distances are calculated using **geodesic distance** on the WGS84 ellipsoid:

```python
from pyproj import Geod
geod = Geod(ellps='WGS84')

# Calculate distance between two points
_, _, distance = geod.inv(lon1, lat1, lon2, lat2)
# distance is in meters
```

This is more accurate than Euclidean distance, especially over longer distances.

### Testing

Run the test suite:

```bash
# Quick test
python test_steiner.py --quick

# Full test with export
python test_steiner.py --export

# Benchmark all subsets
python run_benchmark.py
```

### Performance Tips

1. **Use fast algorithms for large datasets:**
   ```python
   results = pipeline.run_all(algorithms=SteinerPipeline.fast_algorithms())
   ```

2. **Limit terminal count for testing:**
   ```python
   config = PipelineConfig(max_terminals=50)
   ```

3. **Skip full graph export for large networks:**
   ```bash
   python steiner_cli.py run ... --skip-graph-export
   ```

4. **Use GeoPackage for large datasets** (faster I/O than Shapefile):
   ```python
   config = PipelineConfig(export_format="gpkg")
   ```

---
## Acknowledgments

- NetworkX for graph algorithms
- GeoPandas for geospatial data handling
- The Steiner Tree Problem literature