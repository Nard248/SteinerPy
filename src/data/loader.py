"""Road network shapefile loading with region selection."""

from pathlib import Path
from typing import Union

import geopandas as gpd
from shapely.geometry import Polygon, box


class RoadNetworkLoader:
    """Load road network data from shapefiles with flexible region selection."""

    # Default shapefile names for NY road segments
    ROAD_SEGMENT_FILES = ["Trans_RoadSegment_0.shp", "Trans_RoadSegment_1.shp"]

    def __init__(self, data_dir: Union[str, Path] = "Road Data/NY/Shape/"):
        """
        Initialize the loader with the data directory path.

        Args:
            data_dir: Path to directory containing road shapefiles.
        """
        self.data_dir = Path(data_dir)
        self._crs = None  # Will be set on first load

    def _get_shapefile_crs(self) -> str:
        """Get the CRS from the first shapefile (lazy load)."""
        if self._crs is None:
            first_file = self.data_dir / self.ROAD_SEGMENT_FILES[0]
            # Read just the metadata to get CRS
            gdf = gpd.read_file(first_file, rows=1)
            self._crs = gdf.crs
        return self._crs

    def _load_from_files(
        self, bbox: tuple[float, float, float, float] | None = None
    ) -> gpd.GeoDataFrame:
        """
        Load and combine road segments from all shapefile parts.

        Args:
            bbox: Optional (minx, miny, maxx, maxy) in shapefile CRS to filter.

        Returns:
            Combined GeoDataFrame with all road segments.
        """
        gdfs = []
        for filename in self.ROAD_SEGMENT_FILES:
            filepath = self.data_dir / filename
            if filepath.exists():
                gdf = gpd.read_file(filepath, bbox=bbox)
                gdfs.append(gdf)

        if not gdfs:
            raise FileNotFoundError(
                f"No road segment files found in {self.data_dir}"
            )

        combined = gpd.pd.concat(gdfs, ignore_index=True)
        return gpd.GeoDataFrame(combined, crs=gdfs[0].crs)

    def load_roads_bbox(
        self, bbox: tuple[float, float, float, float]
    ) -> gpd.GeoDataFrame:
        """
        Load roads within a bounding box.

        Args:
            bbox: (minx, miny, maxx, maxy) in the shapefile's CRS.

        Returns:
            GeoDataFrame with roads intersecting the bounding box.
        """
        return self._load_from_files(bbox=bbox)

    def load_roads_radius(
        self, center: tuple[float, float], radius_meters: float
    ) -> gpd.GeoDataFrame:
        """
        Load roads within a circular radius of a point.

        Args:
            center: (longitude, latitude) in WGS84.
            radius_meters: Radius in meters.

        Returns:
            GeoDataFrame with roads within the circular area.
        """
        # Create a point in WGS84
        from shapely.geometry import Point

        point_wgs84 = gpd.GeoDataFrame(
            geometry=[Point(center[0], center[1])], crs="EPSG:4326"
        )

        # Get shapefile CRS and transform point
        shapefile_crs = self._get_shapefile_crs()
        point_native = point_wgs84.to_crs(shapefile_crs)

        # For buffering in meters, we need a projected CRS
        # Use UTM zone for the center point for accurate meter distances
        utm_crs = point_wgs84.estimate_utm_crs()
        point_utm = point_wgs84.to_crs(utm_crs)

        # Create buffer in UTM (meters)
        buffer_utm = point_utm.geometry[0].buffer(radius_meters)

        # Convert buffer back to shapefile CRS
        buffer_gdf = gpd.GeoDataFrame(geometry=[buffer_utm], crs=utm_crs)
        buffer_native = buffer_gdf.to_crs(shapefile_crs)
        buffer_polygon = buffer_native.geometry[0]

        # Get bounding box for efficient initial load
        bbox = buffer_polygon.bounds

        # Load roads in bbox
        roads = self._load_from_files(bbox=bbox)

        # Clip to actual circle
        if not roads.empty:
            roads = gpd.clip(roads, buffer_polygon)

        return roads

    def load_roads_polygon(
        self, polygon: Union[Polygon, gpd.GeoDataFrame]
    ) -> gpd.GeoDataFrame:
        """
        Load roads within an arbitrary polygon.

        Args:
            polygon: Shapely Polygon or GeoDataFrame with polygon geometry.
                     If GeoDataFrame, uses the union of all geometries.
                     Should be in shapefile CRS or will be transformed.

        Returns:
            GeoDataFrame with roads clipped to the polygon.
        """
        shapefile_crs = self._get_shapefile_crs()

        # Handle GeoDataFrame input
        if isinstance(polygon, gpd.GeoDataFrame):
            # Transform to shapefile CRS if needed
            if polygon.crs != shapefile_crs:
                polygon = polygon.to_crs(shapefile_crs)
            # Union all geometries
            clip_geom = polygon.union_all()
        else:
            clip_geom = polygon

        # Get bounding box for efficient initial load
        bbox = clip_geom.bounds

        # Load roads in bbox
        roads = self._load_from_files(bbox=bbox)

        # Clip to actual polygon
        if not roads.empty:
            roads = gpd.clip(roads, clip_geom)

        return roads

    def apply_buffer(
        self, gdf: gpd.GeoDataFrame, buffer_meters: float
    ) -> gpd.GeoDataFrame:
        """
        Expand geometries by a buffer distance.

        Args:
            gdf: GeoDataFrame to buffer.
            buffer_meters: Buffer distance in meters.

        Returns:
            GeoDataFrame with buffered geometries.
        """
        original_crs = gdf.crs

        # Buffer in UTM for accurate meter distances
        utm_crs = gdf.estimate_utm_crs()
        gdf_utm = gdf.to_crs(utm_crs)
        gdf_utm["geometry"] = gdf_utm.geometry.buffer(buffer_meters)

        # Convert back to original CRS
        return gdf_utm.to_crs(original_crs)
