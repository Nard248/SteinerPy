# Roadmap: Steiner-AI

## Overview

Build a benchmarking framework that loads NY road network data, snaps location points to the graph, implements both classic approximation algorithms and modern ML-based approaches for the Steiner Tree problem, and provides comprehensive performance comparison across varying problem sizes (100 to 500+ terminals).

## Domain Expertise

None

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Data Foundation** - Load road network shapefiles and build graph representation
- [ ] **Phase 2: Location Integration** - Snap locations to network, generate test subsets
- [ ] **Phase 3: Algorithm Research** - Survey classic and modern Steiner Tree approaches
- [ ] **Phase 4: Classic Algorithms** - Implement MST approximations and shortest-path heuristics
- [ ] **Phase 5: Modern Algorithms** - Implement GNN/RL-based learned approaches
- [ ] **Phase 6: Benchmarking & Output** - Performance framework, export formats, validation

## Phase Details

### Phase 1: Data Foundation
**Goal**: Parse NY road shapefiles into a NetworkX graph with edge weights (distance), node coordinates, and spatial index for queries
**Depends on**: Nothing (first phase)
**Research**: Unlikely (GeoPandas/Shapely/NetworkX are well-documented)
**Plans**: TBD

Plans:
- [ ] 01-01: Shapefile loading and graph construction
- [ ] 01-02: Spatial indexing and graph validation

### Phase 2: Location Integration
**Goal**: Load SQLite location data, snap each point to nearest road edge, generate test subsets of 100/500/1000+ terminals
**Depends on**: Phase 1
**Research**: Unlikely (spatial nearest-neighbor is standard)
**Plans**: TBD

Plans:
- [ ] 02-01: SQLite loading and coordinate snapping
- [ ] 02-02: Test subset generation with size tiers

### Phase 3: Algorithm Research
**Goal**: Document the algorithmic landscape — approximation ratios, complexity, implementation feasibility — to inform implementation choices
**Depends on**: Phase 1 (need graph structure understanding)
**Research**: Likely (literature survey is the deliverable)
**Research topics**: Steiner Tree approximation bounds, Dreyfus-Wagner exact algorithm, MST-based 2-approximation, recent GNN/RL papers, existing benchmark datasets
**Plans**: TBD

Plans:
- [ ] 03-01: Classic algorithm survey and selection
- [ ] 03-02: Modern/ML approach survey and selection

### Phase 4: Classic Algorithms
**Goal**: Implement 2-3 classic approaches: MST-based approximation, shortest-path heuristic, and optionally exact solver for small instances
**Depends on**: Phase 2 (need test data), Phase 3 (need algorithm selection)
**Research**: Likely (implementation details from papers)
**Research topics**: MST-Steiner approximation implementation, Kou-Markowsky-Berman algorithm, ILP formulation for exact solutions
**Plans**: TBD

Plans:
- [ ] 04-01: MST-based 2-approximation
- [ ] 04-02: Shortest-path heuristics
- [ ] 04-03: Exact solver for small instances (optional)

### Phase 5: Modern Algorithms
**Goal**: Implement 1-2 modern approaches: GNN-based solver and/or RL-based learned heuristic
**Depends on**: Phase 2 (need test data), Phase 3 (need algorithm selection)
**Research**: Likely (cutting-edge approaches, API changes)
**Research topics**: GNN architectures for combinatorial optimization, RL formulations for graph problems, PyTorch Geometric setup
**Plans**: TBD

Plans:
- [ ] 05-01: GNN-based approach
- [ ] 05-02: RL-based learned heuristic (optional based on research)

### Phase 6: Benchmarking & Output
**Goal**: Unified benchmark runner with metrics (runtime, solution cost, memory), exportable results (CSV, GeoJSON), and validation against optimal on small instances
**Depends on**: Phase 4, Phase 5
**Research**: Unlikely (standard metrics and export formats)
**Plans**: TBD

Plans:
- [ ] 06-01: Benchmark runner and metrics collection
- [ ] 06-02: Export formats (GeoJSON, edge lists, reports)
- [ ] 06-03: Validation suite and bounds checking

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Foundation | 0/2 | Not started | - |
| 2. Location Integration | 0/2 | Not started | - |
| 3. Algorithm Research | 0/2 | Not started | - |
| 4. Classic Algorithms | 0/3 | Not started | - |
| 5. Modern Algorithms | 0/2 | Not started | - |
| 6. Benchmarking & Output | 0/3 | Not started | - |
