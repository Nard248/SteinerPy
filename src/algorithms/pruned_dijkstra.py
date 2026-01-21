"""Pruned Dijkstra algorithm for Steiner Tree - optimized for road networks."""
from typing import Set, Dict, List, Optional
import networkx as nx
import time
import heapq
from .base import SteinerAlgorithm, AlgorithmResult, AlgorithmRegistry
@AlgorithmRegistry.register
class PrunedDijkstraSteiner(SteinerAlgorithm):
    """
    Optimized Steiner algorithm using pruned multi-source Dijkstra.
    Algorithm:
    1. Run multi-source Dijkstra from all terminals simultaneously
    2. When frontiers meet, record potential connection points
    3. Build MST from connection points using union-find
    4. Reconstruct paths and prune unnecessary branches
    Especially efficient for road networks with natural structure.
    """
    name = "pruned_dijkstra"
    description = "Pruned multi-source Dijkstra optimized for road networks"
    complexity = "O(|V| log |V| + |E|)"
    is_exact = False
    def __init__(self, early_termination: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.early_termination = early_termination
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
        if len(terminals) == 2:
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
        # Multi-source Dijkstra
        dist: Dict[int, float] = {}
        source: Dict[int, int] = {}
        parent: Dict[int, Optional[int]] = {}
        pq = []
        for t in terminals:
            dist[t] = 0
            source[t] = t
            parent[t] = None
            heapq.heappush(pq, (0, t, t))
        connection_edges: List[tuple] = []
        while pq:
            d, u, src = heapq.heappop(pq)
            if u in dist and d > dist[u]:
                continue
            for v in graph.neighbors(u):
                w = graph[u][v].get('weight', 1)
                new_dist = d + w
                if v not in dist:
                    dist[v] = new_dist
                    source[v] = src
                    parent[v] = u
                    heapq.heappush(pq, (new_dist, v, src))
                elif source[v] != src:
                    connection_edges.append((
                        dist[u] + w + dist[v],
                        u, v, source[u], source[v]
                    ))
        if not connection_edges:
            return AlgorithmResult(
                steiner_graph=nx.Graph(), terminals=terminals, steiner_points=set(),
                total_weight=float('inf'), execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name, is_connected=False,
                metadata={"error": "No connections found between terminals"}
            )
        connection_edges.sort()
        terminal_parent = {t: t for t in terminals}
        def find(x):
            if terminal_parent[x] != x:
                terminal_parent[x] = find(terminal_parent[x])
            return terminal_parent[x]
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                terminal_parent[px] = py
                return True
            return False
        selected_edges = []
        for cost, u, v, src_u, src_v in connection_edges:
            if union(src_u, src_v):
                selected_edges.append((u, v, src_u, src_v))
                if len(selected_edges) == len(terminals) - 1:
                    break
        steiner_edges = set()
        def trace_path(node, src_terminal):
            path_edges = []
            current = node
            while parent.get(current) is not None and source.get(current) == src_terminal:
                p = parent[current]
                path_edges.append(tuple(sorted([current, p])))
                current = p
            return path_edges
        for u, v, src_u, src_v in selected_edges:
            steiner_edges.add(tuple(sorted([u, v])))
            steiner_edges.update(trace_path(u, src_u))
            steiner_edges.update(trace_path(v, src_v))
        steiner_graph = self._extract_subgraph(graph, list(steiner_edges))
        steiner_graph = self._prune_leaves(steiner_graph, terminals)
        return AlgorithmResult(
            steiner_graph=steiner_graph, terminals=terminals,
            steiner_points=set(steiner_graph.nodes()) - terminals,
            total_weight=self._compute_total_weight(steiner_graph),
            execution_time=time.perf_counter() - start_time,
            algorithm_name=self.name,
            is_connected=self._check_connectivity(steiner_graph, terminals),
            metadata={"connection_edges_found": len(connection_edges)}
        )
    def _prune_leaves(self, graph: nx.Graph, terminals: Set[int]) -> nx.Graph:
        graph = graph.copy()
        changed = True
        while changed:
            changed = False
            for node in list(graph.nodes()):
                if graph.degree(node) == 1 and node not in terminals:
                    graph.remove_node(node)
                    changed = True
        return graph
