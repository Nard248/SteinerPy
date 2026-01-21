"""Shortest path based Steiner Tree algorithms."""
from typing import Set
import networkx as nx
import time
import heapq
from .base import SteinerAlgorithm, AlgorithmResult, AlgorithmRegistry
@AlgorithmRegistry.register  
class ShortestPathHeuristic(SteinerAlgorithm):
    """Greedy shortest path heuristic for Steiner Tree."""
    name = "shortest_path_heuristic"
    description = "Greedy shortest path heuristic for Steiner Tree"
    complexity = "O(|T| * |V| log |V|)"
    is_exact = False
    def solve(self, graph: nx.Graph, terminals: Set[int], **kwargs) -> AlgorithmResult:
        start_time = time.perf_counter()
        self._validate_inputs(graph, terminals)
        terminals = set(terminals)
        if len(terminals) == 1:
            node = next(iter(terminals))
            subgraph = nx.Graph()
            subgraph.add_node(node, **graph.nodes[node])
            return AlgorithmResult(
                steiner_graph=subgraph, terminals=terminals, steiner_points=set(),
                total_weight=0.0, execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name, is_connected=True
            )
        terminal_list = list(terminals)
        tree_nodes = {terminal_list[0]}
        unconnected = set(terminal_list[1:])
        steiner_edges = set()
        while unconnected:
            best_path, best_dist, best_terminal = None, float('inf'), None
            for terminal in unconnected:
                for tree_node in tree_nodes:
                    try:
                        dist = nx.shortest_path_length(graph, terminal, tree_node, weight='weight')
                        if dist < best_dist:
                            best_dist = dist
                            best_path = nx.shortest_path(graph, terminal, tree_node, weight='weight')
                            best_terminal = terminal
                    except nx.NetworkXNoPath:
                        continue
            if best_path is None:
                break
            for i in range(len(best_path) - 1):
                steiner_edges.add(tuple(sorted([best_path[i], best_path[i + 1]])))
                tree_nodes.update([best_path[i], best_path[i + 1]])
            unconnected.remove(best_terminal)
        steiner_graph = self._extract_subgraph(graph, list(steiner_edges))
        return AlgorithmResult(
            steiner_graph=steiner_graph, terminals=terminals,
            steiner_points=set(steiner_graph.nodes()) - terminals,
            total_weight=self._compute_total_weight(steiner_graph),
            execution_time=time.perf_counter() - start_time,
            algorithm_name=self.name,
            is_connected=self._check_connectivity(steiner_graph, terminals)
        )
@AlgorithmRegistry.register
class DijkstraSteiner(SteinerAlgorithm):
    """Dijkstra-based DP algorithm for small instances."""
    name = "dijkstra_steiner"
    description = "Dijkstra-based DP (exact for small instances)"
    complexity = "O(3^|T| * |V|)"
    is_exact = True
    def __init__(self, max_terminals: int = 12, **kwargs):
        super().__init__(**kwargs)
        self.max_terminals = max_terminals
    def solve(self, graph: nx.Graph, terminals: Set[int], **kwargs) -> AlgorithmResult:
        start_time = time.perf_counter()
        self._validate_inputs(graph, terminals)
        terminals = set(terminals)
        if len(terminals) > self.max_terminals:
            fallback = ShortestPathHeuristic()
            result = fallback.solve(graph, terminals)
            result.algorithm_name = f"{self.name}_fallback"
            result.metadata["fallback"] = True
            return result
        if len(terminals) <= 2:
            return self._solve_small(graph, terminals, start_time)
        return self._solve_dp(graph, terminals, start_time)
    def _solve_small(self, graph, terminals, start_time):
        if len(terminals) == 1:
            node = next(iter(terminals))
            subgraph = nx.Graph()
            subgraph.add_node(node, **graph.nodes[node])
            return AlgorithmResult(
                steiner_graph=subgraph, terminals=terminals, steiner_points=set(),
                total_weight=0.0, execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name, is_connected=True
            )
        t1, t2 = list(terminals)
        try:
            path = nx.shortest_path(graph, t1, t2, weight='weight')
            edges = [(path[i], path[i+1]) for i in range(len(path)-1)]
            steiner_graph = self._extract_subgraph(graph, edges)
            return AlgorithmResult(
                steiner_graph=steiner_graph, terminals=terminals,
                steiner_points=set(steiner_graph.nodes()) - terminals,
                total_weight=self._compute_total_weight(steiner_graph),
                execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name, is_connected=True
            )
        except nx.NetworkXNoPath:
            return AlgorithmResult(
                steiner_graph=nx.Graph(), terminals=terminals, steiner_points=set(),
                total_weight=float('inf'), execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name, is_connected=False
            )
    def _solve_dp(self, graph, terminals, start_time):
        """Solve using Dijkstra-Steiner DP with proper backtracking."""
        terminal_list = list(terminals)
        n_t = len(terminal_list)
        nodes = list(graph.nodes())
        node_idx = {n: i for i, n in enumerate(nodes)}
        idx_node = {i: n for n, i in node_idx.items()}
        n_v = len(nodes)
        INF = float('inf')

        # DP tables
        dp = [[INF] * n_v for _ in range(1 << n_t)]
        # Parent tracking: parent[mask][v] = (parent_type, data)
        # parent_type: 'terminal' (base case), 'merge' (submask merge), 'edge' (relaxation)
        parent = [[None] * n_v for _ in range(1 << n_t)]

        # Base case: single terminals
        for i, t in enumerate(terminal_list):
            mask = 1 << i
            v_idx = node_idx[t]
            dp[mask][v_idx] = 0
            parent[mask][v_idx] = ('terminal', i)

        # DP iteration
        for mask in range(1, 1 << n_t):
            # Merge submasks
            sub = mask
            while sub > 0:
                comp = mask ^ sub
                if comp > 0 and comp < sub:
                    for v in range(n_v):
                        new_cost = dp[sub][v] + dp[comp][v]
                        if new_cost < dp[mask][v]:
                            dp[mask][v] = new_cost
                            parent[mask][v] = ('merge', sub, comp)
                sub = (sub - 1) & mask

            # Dijkstra relaxation
            pq = [(dp[mask][v], v) for v in range(n_v) if dp[mask][v] < INF]
            heapq.heapify(pq)
            while pq:
                d, u = heapq.heappop(pq)
                if d > dp[mask][u]:
                    continue
                for nb in graph.neighbors(nodes[u]):
                    nb_idx = node_idx[nb]
                    w = graph[nodes[u]][nb].get('weight', 1)
                    if d + w < dp[mask][nb_idx]:
                        dp[mask][nb_idx] = d + w
                        parent[mask][nb_idx] = ('edge', u)
                        heapq.heappush(pq, (d + w, nb_idx))

        full = (1 << n_t) - 1
        best_cost = min(dp[full])

        if best_cost == INF:
            return AlgorithmResult(
                steiner_graph=nx.Graph(), terminals=terminals, steiner_points=set(),
                total_weight=INF, execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name, is_connected=False
            )

        # Find root (vertex with minimum cost for full mask)
        root_idx = min(range(n_v), key=lambda v: dp[full][v])

        # Backtrack to reconstruct edges
        edges = set()
        self._backtrack(full, root_idx, parent, dp, graph, nodes, idx_node, node_idx, edges)

        # Build steiner graph
        steiner_graph = self._extract_subgraph(graph, list(edges))

        return AlgorithmResult(
            steiner_graph=steiner_graph, terminals=terminals,
            steiner_points=set(steiner_graph.nodes()) - terminals,
            total_weight=self._compute_total_weight(steiner_graph),
            execution_time=time.perf_counter() - start_time,
            algorithm_name=self.name,
            is_connected=self._check_connectivity(steiner_graph, terminals),
            metadata={"dp_optimal_cost": best_cost, "exact": True}
        )

    def _backtrack(self, mask, v_idx, parent, dp, graph, nodes, idx_node, node_idx, edges):
        """Recursively backtrack to collect edges."""
        if parent[mask][v_idx] is None:
            return

        p = parent[mask][v_idx]

        if p[0] == 'terminal':
            # Base case - single terminal, no edges needed
            return
        elif p[0] == 'merge':
            # Merge of two submasks at vertex v
            _, sub1, sub2 = p
            self._backtrack(sub1, v_idx, parent, dp, graph, nodes, idx_node, node_idx, edges)
            self._backtrack(sub2, v_idx, parent, dp, graph, nodes, idx_node, node_idx, edges)
        elif p[0] == 'edge':
            # Edge from parent vertex
            _, parent_idx = p
            u = nodes[parent_idx]
            v = nodes[v_idx]
            edges.add(tuple(sorted([u, v])))
            self._backtrack(mask, parent_idx, parent, dp, graph, nodes, idx_node, node_idx, edges)
