# src/graph_cache/graph_cache.py

import json
import pickle
import hashlib
from pathlib import Path
from typing import Optional, Tuple

import geopandas as gpd
import networkx as nx

from ..data.graph_builder import GraphBuilder


class GraphCache:
    """
    Disk-backed cache for road network graphs.

    Responsibility:
    - Deterministically cache graphs built from road GeoDataFrames
    - Ensure algorithms never rebuild identical graphs
    - Return BOTH graph and validation report (pipeline expects this)
    """

    def __init__(self, cache_dir: Optional[str] = None):
        # Default to a stable, user-level cache location
        if cache_dir is None:
            cache_dir = Path.home() / ".steinerpy" / "graph_cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Cache key generation
    # ------------------------------------------------------------------

    def _cache_key(
        self,
        roads_gdf: gpd.GeoDataFrame,
        builder: GraphBuilder,
        tag: Optional[str] = None,
    ) -> str:
        """
        Create a deterministic cache key from road geometry + builder params.

        IMPORTANT:
        - Do NOT hash raw geometry bytes (slow + unstable)
        - Use structural metadata instead
        """

        bounds = roads_gdf.total_bounds.tolist() if not roads_gdf.empty else []
        crs = str(roads_gdf.crs)
        n_features = len(roads_gdf)

        key_data = {
            "bounds": bounds,
            "crs": crs,
            "n_features": n_features,
            "coord_precision": builder.coord_precision,
            "snap_tolerance_m": builder.snap_tolerance_meters,
        }

        if tag:
            key_data["tag"] = tag

        key_json = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_json.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_build(
        self,
        roads_gdf: gpd.GeoDataFrame,
        builder: GraphBuilder,
        cache_key: Optional[str] = None,
    ) -> Tuple[nx.Graph, dict]:
        """
        Get cached graph or build it if missing.

        Returns:
            (graph, validation_report)
        """

        if roads_gdf is None or roads_gdf.empty:
            raise ValueError("Cannot build graph from empty roads GeoDataFrame")

        # Resolve cache key
        key = cache_key or self._cache_key(roads_gdf, builder)

        graph_path = self.cache_dir / f"{key}.graph.pkl"
        report_path = self.cache_dir / f"{key}.report.json"

        # --------------------------------------------------------------
        # Cache hit
        # --------------------------------------------------------------
        if graph_path.exists() and report_path.exists():
            with open(graph_path, "rb") as f:
                graph = pickle.load(f)

            with open(report_path, "r") as f:
                report = json.load(f)

            return graph, report

        # --------------------------------------------------------------
        # Cache miss → build once
        # --------------------------------------------------------------
        graph, report = builder.build_and_validate(roads_gdf)

        # Persist to disk
        with open(graph_path, "wb") as f:
            pickle.dump(graph, f, protocol=pickle.HIGHEST_PROTOCOL)

        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        return graph, report
