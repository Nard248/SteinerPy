# Steiner-AI

## What This Is

A benchmarking framework for Steiner Tree algorithms on real road networks. Given a road network and a set of locations (buildings, homes), it finds the shortest subgraph that connects all locations. The project explores both classic and modern algorithmic approaches, comparing solution quality against runtime performance on varying problem sizes.

## Core Value

A scalable algorithm that actually works on 500+ location instances on real road network data.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Data processing pipeline — convert NY shapefiles and SQLite to graph representation
- [ ] Location snapping — snap building/home coordinates to nearest road network edges
- [ ] Test subset generation — create test cases of varying sizes (100, 500, 1000+ locations) from NY data
- [ ] Algorithm research — survey and document classic and modern Steiner Tree approaches
- [ ] Classic algorithm implementations — MST-based approximations, shortest-path heuristics, exact solvers for small instances
- [ ] Modern/ML algorithm implementations — GNN-based, reinforcement learning, learned heuristics
- [ ] Benchmarking framework — measure runtime, solution quality (vs optimal), memory usage
- [ ] Output generation — edge lists, GeoJSON/Shapefile export, metrics reports
- [ ] Validation suite — compare to optimal on small instances, bounds checking, exportable for visual inspection

### Out of Scope

- Visualization/UI — CLI and programmatic API only, no map rendering or interactive interface
- Multi-modal routing — roads only, no rail/transit/trail integration
- Real-time updates — static network, no traffic dynamics or live edge weight changes
- Web service — no REST API or deployment infrastructure

## Context

**Data available:**
- Road network: NY state shapefiles (~880MB across Trans_RoadSegment_0 and Trans_RoadSegment_1)
- Locations: SQLite database (~24MB) with buildings/homes in NY state
- Format: ESRI Shapefiles (.shp/.dbf/.shx/.prj) + SQLite

**Problem domain:**
The Steiner Tree problem in graphs is NP-hard. For real road networks with thousands of nodes, exact solutions are intractable. The project will explore the quality-speed tradeoff frontier across different algorithmic approaches.

**Purpose:**
- Personal deep learning of graph algorithms and GIS data processing
- Potential academic research (benchmarking results, novel approaches)
- Practical tool for GIS applications requiring optimal network coverage

## Constraints

- **Language**: Python with GeoPandas ecosystem as foundation
- **Performance**: C++ extensions may be added later for critical path optimization
- **Data**: Must work with ESRI Shapefile format and SQLite databases
- **Scale**: Target 500+ terminal locations on full NY road network

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + GeoPandas base | Rich GIS ecosystem, rapid prototyping | — Pending |
| Roads only (no multi-modal) | Focused scope, cleaner graph model | — Pending |
| Research-first algorithm selection | Let literature inform implementation choices | — Pending |

---
*Last updated: 2025-01-12 after initialization*
