"""
MST-based Steiner Tree approximation algorithms.

=== THE MST APPROXIMATION APPROACH ===

The key insight: Finding an optimal Steiner tree is NP-hard, but we can use
the Minimum Spanning Tree (MST) of the "metric closure" as a 2-approximation.

Metric Closure: A complete graph on the terminal nodes where each edge weight
is the shortest path distance between those terminals in the original graph.

The 2-approximation means: solution_weight <= 2 * optimal_weight

=== ALGORITHM VISUALIZATION ===

Original Graph (nodes, terminals marked *)         Metric Closure (terminals only)

    *A ─── B ─── *C                                 *A ═══════════════ *C
     │           │                                   ║ ╲               ║
     D ───────── E                    ───►           ║   ╲  (shortest  ║
     │           │                                   ║     ╲  paths)   ║
    *F ───────── G                                 *F ═══════════════ ║

    (roads with distances)                          (complete graph)

MST of Metric Closure:                            Final Steiner Tree:

    *A ═══════════════ *C                          *A ─── B ─── *C
                                                    │
    *F                                              D
                                      ───►          │
    (MST edges)                                    *F

                                                   (actual paths restored)

=== ALGORITHMS IN THIS MODULE ===

1. MSTApproximation: Classic 2-approximation algorithm
   - Guaranteed worst-case bound
   - Good for general use

2. MSTWithSteinerPoints: Enhanced version for road networks
   - Identifies junction nodes as candidate Steiner points
   - May find better solutions on real road data
   - No theoretical guarantee but often better in practice
"""

from typing import Set, Dict, Any, List
import networkx as nx
import time

from .base import SteinerAlgorithm, AlgorithmResult, AlgorithmRegistry


@AlgorithmRegistry.register
class MSTApproximation(SteinerAlgorithm):
    """
    MST-based 2-approximation algorithm for Steiner Tree.

    Algorithm:
    1. Create metric closure graph on terminal nodes (complete graph with
       shortest path distances as edge weights)
    2. Find MST of the metric closure
    3. Replace each MST edge with the actual shortest path in original graph
    4. Remove redundant edges (prune leaves that aren't terminals)

    This is the classic 2-approximation algorithm with O(|T|^2 * |V| log |V|)
    complexity where T is terminals and V is vertices.
    """

    name = "mst_approximation"
    description = "MST-based 2-approximation for Steiner Tree"
    complexity = "O(|T|^2 * |V| log |V|)"
    is_exact = False

    def solve(
        self,
        graph: nx.Graph,
        terminals: Set[int],
        **kwargs
    ) -> AlgorithmResult:
        """Find Steiner tree using MST approximation."""
        start_time = time.perf_counter()
        self._validate_inputs(graph, terminals)

        terminals = set(terminals)

        # Handle trivial cases
        if len(terminals) == 1:
            single_node = next(iter(terminals))
            subgraph = nx.Graph()
            subgraph.add_node(single_node, **graph.nodes[single_node])

            return AlgorithmResult(
                steiner_graph=subgraph,
                terminals=terminals,
                steiner_points=set(),
                total_weight=0.0,
                execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name,
                is_connected=True,
                metadata={"trivial_case": True}
            )

        # Step 1: Compute shortest paths between all pairs of terminals
        terminal_list = list(terminals)
        shortest_paths: Dict[tuple, tuple] = {}  # (u, v) -> (distance, path)

        for i, u in enumerate(terminal_list):
            try:
                distances, paths = nx.single_source_dijkstra(
                    graph, u, weight='weight'
                )
                for j, v in enumerate(terminal_list):
                    if i < j and v in distances:
                        shortest_paths[(u, v)] = (distances[v], paths[v])
                        shortest_paths[(v, u)] = (distances[v], paths[v][::-1])
            except nx.NetworkXError:
                continue

        # Step 2: Build metric closure graph
        metric_closure = nx.Graph()
        for u in terminal_list:
            metric_closure.add_node(u)

        for (u, v), (dist, _) in shortest_paths.items():
            if u < v:  # Avoid duplicates
                metric_closure.add_edge(u, v, weight=dist)

        # Check connectivity of metric closure
        if not nx.is_connected(metric_closure):
            # Find largest connected component of terminals
            components = list(nx.connected_components(metric_closure))
            largest = max(components, key=len)
            reachable_terminals = terminals & largest

            # Re-run on reachable terminals only
            if len(reachable_terminals) > 1:
                terminal_list = list(reachable_terminals)
                metric_closure = metric_closure.subgraph(terminal_list).copy()
            else:
                # Cannot connect multiple terminals
                return AlgorithmResult(
                    steiner_graph=nx.Graph(),
                    terminals=terminals,
                    steiner_points=set(),
                    total_weight=float('inf'),
                    execution_time=time.perf_counter() - start_time,
                    algorithm_name=self.name,
                    is_connected=False,
                    metadata={"error": "Terminals not connected in graph"}
                )

        # Step 3: Find MST of metric closure
        mst_closure = nx.minimum_spanning_tree(metric_closure, weight='weight')

        # Step 4: Replace MST edges with actual paths
        steiner_edges = set()
        for u, v in mst_closure.edges():
            key = (u, v) if (u, v) in shortest_paths else (v, u)
            if key in shortest_paths:
                _, path = shortest_paths[key]
                for i in range(len(path) - 1):
                    edge = tuple(sorted([path[i], path[i + 1]]))
                    steiner_edges.add(edge)

        # Step 5: Build result subgraph
        steiner_graph = self._extract_subgraph(graph, list(steiner_edges))

        # Step 6: Prune non-terminal leaves
        steiner_graph = self._prune_leaves(steiner_graph, terminals)

        # Compute results
        total_weight = self._compute_total_weight(steiner_graph)
        steiner_points = set(steiner_graph.nodes()) - terminals
        is_connected = self._check_connectivity(steiner_graph, terminals)

        return AlgorithmResult(
            steiner_graph=steiner_graph,
            terminals=terminals,
            steiner_points=steiner_points,
            total_weight=total_weight,
            execution_time=time.perf_counter() - start_time,
            algorithm_name=self.name,
            is_connected=is_connected,
            metadata={
                "metric_closure_edges": mst_closure.number_of_edges(),
                "paths_computed": len(shortest_paths) // 2,
            }
        )

    def _prune_leaves(self, graph: nx.Graph, terminals: Set[int]) -> nx.Graph:
        """Remove non-terminal leaf nodes iteratively."""
        graph = graph.copy()
        changed = True

        while changed:
            changed = False
            leaves_to_remove = []

            for node in graph.nodes():
                if graph.degree(node) == 1 and node not in terminals:
                    leaves_to_remove.append(node)

            for leaf in leaves_to_remove:
                graph.remove_node(leaf)
                changed = True

        return graph


@AlgorithmRegistry.register
class MSTWithSteinerPoints(SteinerAlgorithm):
    """
    Enhanced MST algorithm that considers intermediate Steiner points.

    This algorithm improves on basic MST by:
    1. Computing shortest path trees from each terminal
    2. Identifying potential Steiner points (high-degree junction nodes)
    3. Iteratively adding beneficial Steiner points to reduce total cost

    Better for road networks where junction nodes are natural Steiner points.
    """

    name = "mst_steiner_points"
    description = "MST with intelligent Steiner point selection"
    complexity = "O(|T| * |V| log |V| + |V|^2)"
    is_exact = False

    def __init__(self, max_steiner_points: int = 100, **kwargs):
        """
        Initialize algorithm.

        Args:
            max_steiner_points: Maximum number of Steiner points to consider.
        """
        super().__init__(**kwargs)
        self.max_steiner_points = max_steiner_points

    def solve(
        self,
        graph: nx.Graph,
        terminals: Set[int],
        **kwargs
    ) -> AlgorithmResult:
        """Find Steiner tree using enhanced MST with Steiner points."""
        start_time = time.perf_counter()
        self._validate_inputs(graph, terminals)

        terminals = set(terminals)
        max_steiner = kwargs.get('max_steiner_points', self.max_steiner_points)

        # Step 1: Find candidate Steiner points (high-degree nodes near terminals)
        candidate_steiner = self._find_candidate_steiner_points(
            graph, terminals, max_steiner
        )

        # Step 2: Build extended terminal set
        extended_terminals = terminals | candidate_steiner

        # Step 3: Use basic MST approximation on extended set
        mst_algo = MSTApproximation()

        # Temporarily modify to not double-register
        result = mst_algo.solve(graph, extended_terminals)

        # Step 4: Prune unnecessary Steiner points
        steiner_graph = self._prune_leaves(result.steiner_graph, terminals)

        # Recompute steiner points (some candidates might have been pruned)
        steiner_points = set(steiner_graph.nodes()) - terminals
        total_weight = self._compute_total_weight(steiner_graph)
        is_connected = self._check_connectivity(steiner_graph, terminals)

        return AlgorithmResult(
            steiner_graph=steiner_graph,
            terminals=terminals,
            steiner_points=steiner_points,
            total_weight=total_weight,
            execution_time=time.perf_counter() - start_time,
            algorithm_name=self.name,
            is_connected=is_connected,
            metadata={
                "candidate_steiner_points": len(candidate_steiner),
                "final_steiner_points": len(steiner_points),
            }
        )

    def _find_candidate_steiner_points(
        self,
        graph: nx.Graph,
        terminals: Set[int],
        max_points: int
    ) -> Set[int]:
        """Find promising Steiner point candidates."""
        candidates = {}

        # Score each non-terminal node
        for node in graph.nodes():
            if node in terminals:
                continue

            # Score based on:
            # 1. Degree (junction nodes are good)
            # 2. Proximity to terminals
            degree = graph.degree(node)

            # Quick distance estimate using BFS
            try:
                distances = nx.single_source_dijkstra_path_length(
                    graph, node, cutoff=10000, weight='weight'
                )
                terminal_distances = [
                    distances[t] for t in terminals if t in distances
                ]

                if len(terminal_distances) >= 2:
                    avg_dist = sum(terminal_distances) / len(terminal_distances)
                    terminals_reachable = len(terminal_distances)

                    # Higher score = better candidate
                    # Prefer high degree, low distance, many terminals reachable
                    score = (degree * terminals_reachable) / (avg_dist + 1)
                    candidates[node] = score
            except (nx.NetworkXError, nx.NetworkXNoPath, KeyError):
                continue

        # Select top candidates
        sorted_candidates = sorted(candidates.items(), key=lambda x: -x[1])
        return set(node for node, _ in sorted_candidates[:max_points])

    def _prune_leaves(self, graph: nx.Graph, terminals: Set[int]) -> nx.Graph:
        """Remove non-terminal leaf nodes iteratively."""
        graph = graph.copy()
        changed = True

        while changed:
            changed = False
            leaves_to_remove = []

            for node in graph.nodes():
                if graph.degree(node) == 1 and node not in terminals:
                    leaves_to_remove.append(node)

            for leaf in leaves_to_remove:
                graph.remove_node(leaf)
                changed = True

        return graph
