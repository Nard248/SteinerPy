"""Export utilities for Steiner Network results to various GIS formats."""

from pathlib import Path
from typing import Dict, List, Optional, Set, Union
import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import LineString, Point, MultiLineString


# Common CRS options
CRS_WGS84 = "EPSG:4326"
CRS_NA_ALBERS = "ESRI:102008"  # North America Albers Equal Area Conic

# Export formats
FORMAT_SHP = "shp"
FORMAT_GPKG = "gpkg"


class SteinerExporter:
    """Export Steiner network results to GIS formats."""

    def __init__(
        self,
        output_dir: Union[str, Path],
        crs: str = CRS_WGS84,
        export_format: str = FORMAT_SHP
    ):
        """
        Initialize exporter.

        Args:
            output_dir: Directory to save output files
            crs: Coordinate reference system (EPSG:4326 or ESRI:102008)
            export_format: Output format ('shp' for Shapefile, 'gpkg' for GeoPackage)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.crs = crs
        self.export_format = export_format.lower()
        self._ext = ".shp" if self.export_format == FORMAT_SHP else ".gpkg"
        self._driver = None if self.export_format == FORMAT_SHP else "GPKG"

    def _save_gdf(self, gdf: gpd.GeoDataFrame, base_filename: str) -> Path:
        """Save GeoDataFrame in the configured format."""
        # Remove extension if provided
        base_name = base_filename.replace('.shp', '').replace('.gpkg', '')
        output_path = self.output_dir / f"{base_name}{self._ext}"

        if self.crs != CRS_WGS84:
            gdf = gdf.to_crs(self.crs)

        if self._driver:
            gdf.to_file(output_path, driver=self._driver)
        else:
            gdf.to_file(output_path)
        return output_path

    def export_graph_nodes(
        self,
        graph: nx.Graph,
        filename: str = "graph_nodes",
        terminals: Optional[Set[int]] = None
    ) -> Path:
        """
        Export graph nodes as point shapefile.

        Args:
            graph: NetworkX graph with node coordinates
            filename: Output filename (without extension)
            terminals: Optional set of terminal node IDs to mark

        Returns:
            Path to created file
        """
        nodes_data = []
        for node_id in graph.nodes():
            node_data = graph.nodes[node_id]
            if 'x' not in node_data or 'y' not in node_data:
                continue

            is_terminal = terminals is not None and node_id in terminals
            degree = graph.degree(node_id)

            nodes_data.append({
                'node_id': node_id,
                'x': node_data['x'],
                'y': node_data['y'],
                'degree': degree,
                'is_terminal': is_terminal,
                'node_type': 'terminal' if is_terminal else ('junction' if degree > 2 else 'intermediate'),
                'geometry': Point(node_data['x'], node_data['y'])
            })

        gdf = gpd.GeoDataFrame(nodes_data, crs=CRS_WGS84)
        return self._save_gdf(gdf, filename)

    def export_graph_edges(
        self,
        graph: nx.Graph,
        filename: str = "graph_edges"
    ) -> Path:
        """
        Export graph edges as line shapefile.

        Args:
            graph: NetworkX graph with edge geometries
            filename: Output filename (without extension)

        Returns:
            Path to created file
        """
        edges_data = []
        for u, v, data in graph.edges(data=True):
            # Get geometry from edge data or create from nodes
            if 'geometry' in data:
                geom = data['geometry']
            else:
                u_data = graph.nodes[u]
                v_data = graph.nodes[v]
                if 'x' in u_data and 'x' in v_data:
                    geom = LineString([
                        (u_data['x'], u_data['y']),
                        (v_data['x'], v_data['y'])
                    ])
                else:
                    continue

            weight = data.get('weight', 0)

            edges_data.append({
                'from_node': u,
                'to_node': v,
                'weight_m': weight,
                'weight_km': weight / 1000.0,
                'weight_mi': weight / 1609.34,
                'geometry': geom
            })

        gdf = gpd.GeoDataFrame(edges_data, crs=CRS_WGS84)
        return self._save_gdf(gdf, filename)

    def export_terminals(
        self,
        graph: nx.Graph,
        terminals: Set[int],
        location_mapping: Optional[Dict[int, int]] = None,
        filename: str = "terminals.shp"
    ) -> Path:
        """
        Export terminal (snap) points as shapefile.

        Args:
            graph: NetworkX graph
            terminals: Set of terminal node IDs
            location_mapping: Optional mapping from location index to node ID
            filename: Output filename

        Returns:
            Path to created file
        """
        terminals_data = []

        # Reverse mapping if provided
        node_to_locations = {}
        if location_mapping:
            for loc_idx, node_id in location_mapping.items():
                if node_id not in node_to_locations:
                    node_to_locations[node_id] = []
                node_to_locations[node_id].append(loc_idx)

        for node_id in terminals:
            node_data = graph.nodes.get(node_id, {})
            if 'x' not in node_data or 'y' not in node_data:
                continue

            locations_count = len(node_to_locations.get(node_id, []))

            terminals_data.append({
                'node_id': node_id,
                'x': node_data['x'],
                'y': node_data['y'],
                'degree': graph.degree(node_id),
                'loc_count': locations_count,  # Number of locations snapped to this node
                'geometry': Point(node_data['x'], node_data['y'])
            })

        gdf = gpd.GeoDataFrame(terminals_data, crs=CRS_WGS84)
        return self._save_gdf(gdf, filename)

    def export_solution(
        self,
        result,  # AlgorithmResult
        graph: nx.Graph,
        filename_prefix: str = "solution"
    ) -> Dict[str, Path]:
        """
        Export Steiner solution (edges and nodes) as shapefiles.

        Args:
            result: AlgorithmResult from algorithm
            graph: Original full graph
            filename_prefix: Prefix for output files

        Returns:
            Dict with paths to created files
        """
        paths = {}

        # Export solution edges
        edges_data = []
        total_weight = 0

        for u, v, data in result.steiner_graph.edges(data=True):
            weight = data.get('weight', 0)
            total_weight += weight

            if 'geometry' in data:
                geom = data['geometry']
            else:
                u_data = result.steiner_graph.nodes[u]
                v_data = result.steiner_graph.nodes[v]
                geom = LineString([
                    (u_data['x'], u_data['y']),
                    (v_data['x'], v_data['y'])
                ])

            # Determine edge type
            u_is_terminal = u in result.terminals
            v_is_terminal = v in result.terminals
            if u_is_terminal and v_is_terminal:
                edge_type = "terminal-terminal"
            elif u_is_terminal or v_is_terminal:
                edge_type = "terminal-steiner"
            else:
                edge_type = "steiner-steiner"

            edges_data.append({
                'from_node': u,
                'to_node': v,
                'weight_m': weight,
                'weight_km': weight / 1000.0,
                'weight_mi': weight / 1609.34,
                'edge_type': edge_type,
                'algorithm': result.algorithm_name,
                'geometry': geom
            })

        if edges_data:
            gdf_edges = gpd.GeoDataFrame(edges_data, crs=CRS_WGS84)
            edge_path = self._save_gdf(gdf_edges, f"{filename_prefix}_edges")
            paths['edges'] = edge_path

        # Export solution nodes
        nodes_data = []
        for node_id in result.steiner_graph.nodes():
            node_data = result.steiner_graph.nodes[node_id]
            if 'x' not in node_data or 'y' not in node_data:
                continue

            is_terminal = node_id in result.terminals
            is_steiner = node_id in result.steiner_points

            nodes_data.append({
                'node_id': node_id,
                'x': node_data['x'],
                'y': node_data['y'],
                'degree': result.steiner_graph.degree(node_id),
                'is_terminal': is_terminal,
                'is_steiner': is_steiner,
                'node_type': 'terminal' if is_terminal else 'steiner',
                'algorithm': result.algorithm_name,
                'geometry': Point(node_data['x'], node_data['y'])
            })

        if nodes_data:
            gdf_nodes = gpd.GeoDataFrame(nodes_data, crs=CRS_WGS84)
            node_path = self._save_gdf(gdf_nodes, f"{filename_prefix}_nodes")
            paths['nodes'] = node_path

        return paths

    def export_benchmark_solutions(
        self,
        results: Dict[str, "AlgorithmResult"],
        graph: nx.Graph,
        terminals: Set[int]
    ) -> Dict[str, Dict[str, Path]]:
        """
        Export all benchmark solutions to separate shapefiles.

        Args:
            results: Dict mapping algorithm name to AlgorithmResult
            graph: Original full graph
            terminals: Set of terminal nodes

        Returns:
            Nested dict with paths for each algorithm
        """
        all_paths = {}

        for algo_name, result in results.items():
            safe_name = algo_name.replace(" ", "_").replace("-", "_")
            paths = self.export_solution(result, graph, filename_prefix=f"solution_{safe_name}")
            all_paths[algo_name] = paths

        return all_paths

    def export_mileage_summary(
        self,
        results: Dict[str, "AlgorithmResult"],
        filename: str = "mileage_summary.csv"
    ) -> Path:
        """
        Export mileage/distance summary for all algorithms.

        Args:
            results: Dict mapping algorithm name to AlgorithmResult
            filename: Output CSV filename

        Returns:
            Path to created file
        """
        summary_data = []

        for algo_name, result in results.items():
            total_meters = result.total_weight

            summary_data.append({
                'algorithm': algo_name,
                'total_meters': total_meters,
                'total_kilometers': total_meters / 1000.0,
                'total_miles': total_meters / 1609.34,
                'total_feet': total_meters * 3.28084,
                'node_count': result.node_count,
                'edge_count': result.edge_count,
                'terminal_count': len(result.terminals),
                'steiner_point_count': len(result.steiner_points),
                'is_connected': result.is_connected,
                'execution_time_sec': result.execution_time
            })

        df = pd.DataFrame(summary_data)
        df = df.sort_values('total_meters')

        output_path = self.output_dir / filename
        df.to_csv(output_path, index=False)

        # Also create a shapefile-friendly version (point at centroid with attributes)
        return output_path

    def export_full_debug_package(
        self,
        graph: nx.Graph,
        terminals: Set[int],
        results: Dict[str, "AlgorithmResult"],
        location_mapping: Optional[Dict[int, int]] = None,
        include_full_graph: bool = True
    ) -> Dict[str, Path]:
        """
        Export complete debug package with all layers.

        Creates:
        - graph_nodes.shp: All graph nodes
        - graph_edges.shp: All graph edges (full road network)
        - terminals.shp: Terminal/snap points
        - solution_<algo>_edges.shp: Solution edges per algorithm
        - solution_<algo>_nodes.shp: Solution nodes per algorithm
        - mileage_summary.csv: Summary statistics

        Args:
            graph: Full road network graph
            terminals: Terminal node IDs
            results: Algorithm results
            location_mapping: Location to node mapping
            include_full_graph: Whether to export full graph (can be large)

        Returns:
            Dict with all created file paths
        """
        all_paths = {}

        print(f"Exporting debug package to: {self.output_dir}")
        print(f"  CRS: {self.crs}")

        # Export full graph
        if include_full_graph:
            print("  Exporting full graph nodes...")
            all_paths['graph_nodes'] = self.export_graph_nodes(graph, terminals=terminals)
            print(f"    -> {all_paths['graph_nodes']}")

            print("  Exporting full graph edges...")
            all_paths['graph_edges'] = self.export_graph_edges(graph)
            print(f"    -> {all_paths['graph_edges']}")

        # Export terminals
        print("  Exporting terminals...")
        all_paths['terminals'] = self.export_terminals(graph, terminals, location_mapping)
        print(f"    -> {all_paths['terminals']}")

        # Export solutions
        print("  Exporting solutions...")
        solution_paths = self.export_benchmark_solutions(results, graph, terminals)
        for algo_name, paths in solution_paths.items():
            for layer_type, path in paths.items():
                key = f"solution_{algo_name}_{layer_type}"
                all_paths[key] = path
                print(f"    -> {path}")

        # Export mileage summary
        print("  Exporting mileage summary...")
        all_paths['mileage_summary'] = self.export_mileage_summary(results)
        print(f"    -> {all_paths['mileage_summary']}")

        print(f"\nExport complete! {len(all_paths)} files created.")

        return all_paths


def quick_export(
    output_dir: str,
    graph: nx.Graph,
    terminals: Set[int],
    results: Dict[str, "AlgorithmResult"],
    crs: str = CRS_WGS84,
    export_format: str = FORMAT_SHP,
    location_mapping: Optional[Dict[int, int]] = None
) -> Dict[str, Path]:
    """
    Convenience function for quick export of all debug data.

    Args:
        output_dir: Output directory path
        graph: Full road network graph
        terminals: Terminal node IDs
        results: Algorithm results dict
        crs: Target CRS (EPSG:4326 or ESRI:102008)
        export_format: Output format ('shp' or 'gpkg')
        location_mapping: Optional location to node mapping

    Returns:
        Dict with all created file paths
    """
    exporter = SteinerExporter(output_dir, crs=crs, export_format=export_format)
    return exporter.export_full_debug_package(
        graph=graph,
        terminals=terminals,
        results=results,
        location_mapping=location_mapping
    )
