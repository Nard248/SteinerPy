"""Pruned Dijkstra algorithm for Steiner Tree - optimized for road networks."""
from typing import Set, Dict, List, Optional, Tuple
import networkx as nx
import time
import heapq
from .base import SteinerAlgorithm, AlgorithmResult, AlgorithmRegistry


@AlgorithmRegistry.register
class PrunedDijkstraSteiner(SteinerAlgorithm):
    """
    Pruned multi-source Dijkstra Steiner approximation for road networks.

    - Proper Dijkstra relaxation with region stealing
    - Slack-filtered boundary detection
    - Steiner hub promotion
    - Per-connected-component execution
    - Returns a FOREST (finite) when terminals are isolated
    """
    name = "pruned_dijkstra"
    description = "Pruned multi-source Dijkstra optimized for road networks"
    complexity = "O(|E| log |V|)"
    is_exact = False

    def __init__(self, early_termination: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.early_termination = early_termination

        # Quality knobs
        self.epsilon = float(kwargs.pop("epsilon", 0.15))
        self.hub_threshold = int(kwargs.pop("hub_threshold", 3))
        self.max_hubs = int(kwargs.pop("max_hubs", 50))
        self.hub_bonus = float(kwargs.pop("hub_bonus", 0.0))

    def solve(self, graph: nx.Graph, terminals: Set[int], **kwargs) -> AlgorithmResult:
        start_time = time.perf_counter()
        self._validate_inputs(graph, terminals)
        terminals = set(terminals)

        # Global trivial case
        if len(terminals) == 1:
            t = next(iter(terminals))
            g = nx.Graph()
            g.add_node(t, **graph.nodes[t])
            return AlgorithmResult(
                steiner_graph=g,
                terminals=terminals,
                steiner_points=set(),
                total_weight=0.0,
                execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name,
                is_connected=True,
            )

        # --------------------------------------------------
        # Connected components
        # --------------------------------------------------
        components = list(nx.connected_components(graph))
        node_component: Dict[int, int] = {}
        for i, comp in enumerate(components):
            for n in comp:
                node_component[n] = i

        # Group terminals by component
        terminals_by_comp: Dict[int, Set[int]] = {}
        for t in terminals:
            c = node_component.get(t)
            if c is not None:
                terminals_by_comp.setdefault(c, set()).add(t)

        # --------------------------------------------------
        # Global accumulators
        # --------------------------------------------------
        all_steiner_edges: Set[Tuple[int, int]] = set()
        isolated_terminals: Set[int] = set()
        per_comp_stats = {}

        total_boundary_pairs = 0
        total_selected_edges = 0
        total_hubs = 0

        # --------------------------------------------------
        # Solve per component
        # --------------------------------------------------
        for comp_id, comp_terminals in terminals_by_comp.items():
            comp_nodes = components[comp_id]
            subgraph = graph.subgraph(comp_nodes)

            # Case 1: isolated terminal → keep node only
            if len(comp_terminals) == 1:
                t = next(iter(comp_terminals))
                isolated_terminals.add(t)
                per_comp_stats[comp_id] = {
                    "terminals": 1,
                    "status": "isolated_terminal",
                }
                continue

            # Case 2: exactly two terminals → shortest path
            if len(comp_terminals) == 2:
                t1, t2 = list(comp_terminals)
                try:
                    path = nx.shortest_path(subgraph, t1, t2, weight="weight")
                    for i in range(len(path) - 1):
                        all_steiner_edges.add(tuple(sorted((path[i], path[i + 1]))))
                    per_comp_stats[comp_id] = {
                        "terminals": 2,
                        "status": "direct_shortest_path",
                    }
                except nx.NetworkXNoPath:
                    isolated_terminals.update(comp_terminals)
                    per_comp_stats[comp_id] = {
                        "terminals": 2,
                        "status": "no_path",
                    }
                continue

            # --------------------------------------------------
            # Multi-source Dijkstra
            # --------------------------------------------------
            dist: Dict[int, float] = {}
            source: Dict[int, int] = {}
            parent: Dict[int, Optional[int]] = {}
            pq: List[Tuple[float, int, int]] = []

            for t in comp_terminals:
                dist[t] = 0.0
                source[t] = t
                parent[t] = None
                heapq.heappush(pq, (0.0, t, t))

            best_boundary: Dict[Tuple[int, int], Tuple[float, int, int, int, int]] = {}
            boundary_hits: Dict[int, int] = {}

            while pq:
                d, u, src = heapq.heappop(pq)
                if dist.get(u, float("inf")) < d:
                    continue

                src_u = source[u]

                for v in subgraph.neighbors(u):
                    w = subgraph[u][v].get("weight", 1.0)
                    new_dist = d + w
                    dv = dist.get(v)

                    if dv is None or new_dist < dv:
                        dist[v] = new_dist
                        source[v] = src_u
                        parent[v] = u
                        heapq.heappush(pq, (new_dist, v, src_u))
                        continue

                    # Boundary candidate (UNFILTERED – REQUIRED for road graphs)
                    src_v = source.get(v)
                    if src_v is not None and src_v != src_u:
                        cost = d + w + dist[v]

                        boundary_hits[u] = boundary_hits.get(u, 0) + 1
                        boundary_hits[v] = boundary_hits.get(v, 0) + 1

                        a, b = (src_u, src_v) if src_u < src_v else (src_v, src_u)
                        prev = best_boundary.get((a, b))
                        if prev is None or cost < prev[0]:
                            best_boundary[(a, b)] = (cost, u, v, src_u, src_v)

            if not best_boundary:
                isolated_terminals.update(comp_terminals)
                per_comp_stats[comp_id] = {
                    "terminals": len(comp_terminals),
                    "status": "no_boundary_pairs",
                }
                continue

            connection_edges = sorted(best_boundary.values(), key=lambda x: x[0])

            # --------------------------------------------------
            # Steiner hubs
            # --------------------------------------------------
            hubs = [n for n, c in boundary_hits.items() if c >= self.hub_threshold]
            hubs.sort(key=lambda n: boundary_hits[n], reverse=True)
            hubs = hubs[: self.max_hubs]

            mst_nodes = set(comp_terminals) | set(hubs)
            mst_edges: List[Tuple[float, int, int, int, int]] = []
            mst_edges.extend(connection_edges)

            for h in hubs:
                sh = source.get(h)
                if sh is not None:
                    mst_edges.append((dist[h] + self.hub_bonus, h, h, sh, h))

            # --------------------------------------------------
            # MST (Kruskal)
            # --------------------------------------------------
            uf = {n: n for n in mst_nodes}

            def find(x):
                while uf[x] != x:
                    uf[x] = uf[uf[x]]
                    x = uf[x]
                return x

            def union(a, b):
                ra, rb = find(a), find(b)
                if ra != rb:
                    uf[ra] = rb
                    return True
                return False

            selected_edges = []
            mst_edges.sort(key=lambda x: x[0])
            for cost, u, v, su, sv in mst_edges:
                if union(su, sv):
                    selected_edges.append((u, v, su, sv))
                    if len(selected_edges) == len(mst_nodes) - 1:
                        break

            if len(selected_edges) < len(mst_nodes) - 1:
                isolated_terminals.update(comp_terminals)
                per_comp_stats[comp_id] = {
                    "terminals": len(comp_terminals),
                    "status": "mst_incomplete",
                }
                continue

            # --------------------------------------------------
            # Reconstruct paths
            # --------------------------------------------------
            def trace(node, src):
                out = []
                seen = set()
                cur = node
                while cur not in seen:
                    seen.add(cur)
                    p = parent.get(cur)
                    if p is None or source.get(cur) != src:
                        break
                    out.append(tuple(sorted((cur, p))))
                    cur = p
                return out

            steiner_edges = set()
            for u, v, su, sv in selected_edges:
                if u == v:
                    steiner_edges.update(trace(u, su))
                else:
                    steiner_edges.add(tuple(sorted((u, v))))
                    steiner_edges.update(trace(u, su))
                    steiner_edges.update(trace(v, sv))

            all_steiner_edges.update(steiner_edges)

            per_comp_stats[comp_id] = {
                "terminals": len(comp_terminals),
                "hubs": len(hubs),
                "boundary_pairs": len(best_boundary),
                "selected_edges": len(selected_edges),
                "status": "ok",
            }
            total_boundary_pairs += len(best_boundary)
            total_selected_edges += len(selected_edges)
            total_hubs += len(hubs)

        # --------------------------------------------------
        # Final assembly (FOREST)
        # --------------------------------------------------
        steiner_graph = self._extract_subgraph(graph, list(all_steiner_edges))

        # Ensure isolated terminals are kept
        for t in isolated_terminals:
            steiner_graph.add_node(t, **graph.nodes[t])

        steiner_graph = self._prune_leaves(steiner_graph, terminals)

        return AlgorithmResult(
            steiner_graph=steiner_graph,
            terminals=terminals,
            steiner_points=set(steiner_graph.nodes()) - terminals,
            total_weight=self._compute_total_weight(steiner_graph),
            execution_time=time.perf_counter() - start_time,
            algorithm_name=self.name,
            is_connected=False,  # forest, not a single tree
            metadata={
                "per_component": per_comp_stats,
                "isolated_terminals": list(isolated_terminals),
                "total_boundary_pairs": total_boundary_pairs,
                "total_selected_edges": total_selected_edges,
                "total_hubs": total_hubs,
                "components_with_terminals": len(terminals_by_comp),
            },
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
