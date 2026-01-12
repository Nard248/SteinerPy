# Road Network Subsets

**Center point:** 42.6526N, 73.7562W (Albany, NY)

## Subsets

| Name | Radius | Road Segments | Description |
|------|--------|---------------|-------------|
| xs | 1km | 676 | Extra small - ~1km radius, neighborhood scale |
| s | 5km | 5,101 | Small - ~5km radius, small town scale |
| m | 10km | 13,050 | Medium - ~10km radius, city scale |
| l | 25km | 35,932 | Large - ~25km radius, county scale |
| xl | 50km | 65,443 | Extra large - ~50km radius, regional scale |

## Usage

```python
import geopandas as gpd

# Load a subset
roads = gpd.read_file("data/subsets/roads/m.gpkg")
```

## File Format

All subsets are saved as GeoPackage (.gpkg) files, which:
- Support efficient spatial queries
- Preserve CRS and attribute information
- Are widely supported by GIS tools
