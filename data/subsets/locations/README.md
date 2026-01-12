# Location Subsets

**Status:** To be generated in Phase 2 (Location Integration)

Location subsets will contain snapped building/home coordinates at various sizes:
- Terminal counts: 100, 250, 500, 1000, 2000+
- Each matched to corresponding road network subsets

## Planned Structure

```
locations/
  xs_100.gpkg    # 100 locations in XS road network
  s_250.gpkg     # 250 locations in S road network
  m_500.gpkg     # 500 locations in M road network
  l_1000.gpkg    # 1000 locations in L road network
  xl_2000.gpkg   # 2000 locations in XL road network
```
