"""Generate and save road network subsets at various sizes for benchmarking."""

from pathlib import Path
from typing import NamedTuple

import geopandas as gpd

from .loader import RoadNetworkLoader


class SubsetConfig(NamedTuple):
    """Configuration for a road network subset."""

    name: str
    radius_meters: float
    description: str


# Default subset sizes - centered on Albany, NY
DEFAULT_SUBSETS = [
    SubsetConfig("xs", 1_000, "Extra small - ~1km radius, neighborhood scale"),
    SubsetConfig("s", 5_000, "Small - ~5km radius, small town scale"),
    SubsetConfig("m", 10_000, "Medium - ~10km radius, city scale"),
    SubsetConfig("l", 25_000, "Large - ~25km radius, county scale"),
    SubsetConfig("xl", 50_000, "Extra large - ~50km radius, regional scale"),
]

# Default center point: Albany, NY (state capital, good road network density)
DEFAULT_CENTER = (-73.7562, 42.6526)


class SubsetGenerator:
    """Generate and manage road network subsets for benchmarking."""

    def __init__(
        self,
        data_dir: str | Path = "Road Data/NY/Shape/",
        output_dir: str | Path = "data/subsets/roads/",
    ):
        """
        Initialize the subset generator.

        Args:
            data_dir: Path to source shapefile directory.
            output_dir: Path to save generated subsets.
        """
        self.loader = RoadNetworkLoader(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_subset(
        self,
        name: str,
        center: tuple[float, float],
        radius_meters: float,
        description: str = "",
    ) -> gpd.GeoDataFrame:
        """
        Generate and save a road network subset.

        Args:
            name: Subset name (used for filename).
            center: (longitude, latitude) center point in WGS84.
            radius_meters: Radius in meters.
            description: Optional description for metadata.

        Returns:
            The generated GeoDataFrame.
        """
        print(f"Generating subset '{name}' ({radius_meters/1000:.0f}km radius)...")

        # Load roads within radius
        roads = self.loader.load_roads_radius(center, radius_meters)

        # Save to GeoPackage
        output_path = self.output_dir / f"{name}.gpkg"
        roads.to_file(output_path, driver="GPKG")

        print(f"  Saved {len(roads)} road segments to {output_path}")

        return roads

    def generate_all_defaults(
        self,
        center: tuple[float, float] = DEFAULT_CENTER,
        subsets: list[SubsetConfig] | None = None,
    ) -> dict[str, gpd.GeoDataFrame]:
        """
        Generate all default subsets.

        Args:
            center: Center point for all subsets.
            subsets: List of subset configs, defaults to DEFAULT_SUBSETS.

        Returns:
            Dictionary mapping subset names to GeoDataFrames.
        """
        if subsets is None:
            subsets = DEFAULT_SUBSETS

        results = {}
        for config in subsets:
            gdf = self.generate_subset(
                name=config.name,
                center=center,
                radius_meters=config.radius_meters,
                description=config.description,
            )
            results[config.name] = gdf

        # Generate summary
        self._write_summary(results, center, subsets)

        return results

    def _write_summary(
        self,
        results: dict[str, gpd.GeoDataFrame],
        center: tuple[float, float],
        subsets: list[SubsetConfig],
    ) -> None:
        """Write a summary file with subset statistics."""
        summary_path = self.output_dir / "README.md"

        lines = [
            "# Road Network Subsets",
            "",
            f"**Center point:** {center[1]:.4f}N, {abs(center[0]):.4f}W (Albany, NY)",
            "",
            "## Subsets",
            "",
            "| Name | Radius | Road Segments | Description |",
            "|------|--------|---------------|-------------|",
        ]

        for config in subsets:
            gdf = results[config.name]
            lines.append(
                f"| {config.name} | {config.radius_meters/1000:.0f}km | "
                f"{len(gdf):,} | {config.description} |"
            )

        lines.extend(
            [
                "",
                "## Usage",
                "",
                "```python",
                "import geopandas as gpd",
                "",
                '# Load a subset',
                'roads = gpd.read_file("data/subsets/roads/m.gpkg")',
                "```",
                "",
                "## File Format",
                "",
                "All subsets are saved as GeoPackage (.gpkg) files, which:",
                "- Support efficient spatial queries",
                "- Preserve CRS and attribute information",
                "- Are widely supported by GIS tools",
                "",
            ]
        )

        summary_path.write_text("\n".join(lines))
        print(f"\nSummary written to {summary_path}")

    def load_subset(self, name: str) -> gpd.GeoDataFrame:
        """
        Load a previously generated subset.

        Args:
            name: Subset name (xs, s, m, l, xl).

        Returns:
            GeoDataFrame with road segments.
        """
        path = self.output_dir / f"{name}.gpkg"
        if not path.exists():
            raise FileNotFoundError(
                f"Subset '{name}' not found. Run generate_all_defaults() first."
            )
        return gpd.read_file(path)

    def list_subsets(self) -> list[str]:
        """List available subset names."""
        return [p.stem for p in self.output_dir.glob("*.gpkg")]


def main():
    """Generate all default road network subsets."""
    generator = SubsetGenerator()
    generator.generate_all_defaults()
    print("\nDone! All subsets generated.")


if __name__ == "__main__":
    main()
