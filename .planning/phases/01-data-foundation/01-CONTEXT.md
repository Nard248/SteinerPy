# Phase 1: Data Foundation - Context

**Gathered:** 2025-01-12
**Status:** Ready for planning

<vision>
## How This Should Work

We're not loading the full 880MB dataset. Instead, this is a subset-based approach:

1. **Pick locations** using flexible selection methods — bounding box, county/region names, or point + radius. Support all three, pick at runtime based on the experiment.

2. **Cut roads** using a buffer around the selected locations. Take some mileage buffer around the location set, clip the road network to that buffer, then build the graph from the clipped roads.

3. **Fresh graph each run** — no caching layer. The graph gets constructed for each new input/region selection. Data preprocessing is separate from the main algorithm flow.

4. **GeoPandas as the foundation** — it's a good handler for this kind of GIS work in Python.

The workflow: select a region → clip roads to buffer → build graph → hand off to algorithms.

</vision>

<essential>
## What Must Be Nailed

- **Correct graph topology** — edges must connect properly at intersections, no broken or dangling segments, valid network that algorithms can traverse. This is the non-negotiable. If the graph is wrong, everything downstream fails.

</essential>

<boundaries>
## What's Out of Scope

- Visualization — no map rendering, no interactive displays. Just data structures.
- Location snapping to roads — that's Phase 2's job. This phase builds the road graph only.

</boundaries>

<specifics>
## Specific Ideas

- Multiple selection methods (bbox, county, point+radius) supported from the start
- Buffer approach is flexible — convex hull, individual buffers merged, or simple bounding box padding — whatever works best
- Use GeoPandas for shapefile handling

</specifics>

<notes>
## Additional Context

The emphasis is on getting a correct, usable graph from arbitrary subsets of the NY road network. Performance optimization can come later — correctness first.

This phase produces the road graph. Phase 2 adds location data and snapping. The clean separation means the graph construction can be tested independently.

</notes>

---

*Phase: 01-data-foundation*
*Context gathered: 2025-01-12*
