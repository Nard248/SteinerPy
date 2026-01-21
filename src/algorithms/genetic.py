"""Genetic algorithm for Steiner Tree optimization."""

from typing import Set, List
import networkx as nx
import numpy as np
import time
import random

from .base import SteinerAlgorithm, AlgorithmResult, AlgorithmRegistry


@AlgorithmRegistry.register
class GeneticSteiner(SteinerAlgorithm):
    """Genetic algorithm for Steiner Tree optimization."""

    name = "genetic"
    description = "Genetic algorithm for Steiner Tree optimization"
    complexity = "O(generations * population * |V| log |V|)"
    is_exact = False

    def __init__(self, population_size: int = 50, generations: int = 100,
                 mutation_rate: float = 0.1, elite_ratio: float = 0.1, **kwargs):
        super().__init__(**kwargs)
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elite_ratio = elite_ratio

    def solve(self, graph: nx.Graph, terminals: Set[int], **kwargs) -> AlgorithmResult:
        start_time = time.perf_counter()
        self._validate_inputs(graph, terminals)
        terminals = set(terminals)

        if len(terminals) <= 2:
            return self._solve_trivial(graph, terminals, start_time)

        all_nodes = set(graph.nodes())
        non_terminals = list(all_nodes - terminals)

        if not non_terminals:
            terminal_graph = graph.subgraph(terminals)
            if nx.is_connected(terminal_graph):
                mst = nx.minimum_spanning_tree(terminal_graph, weight='weight')
                return AlgorithmResult(
                    steiner_graph=mst, terminals=terminals, steiner_points=set(),
                    total_weight=self._compute_total_weight(mst),
                    execution_time=time.perf_counter() - start_time,
                    algorithm_name=self.name, is_connected=True
                )

        population = self._initialize_population(graph, terminals, non_terminals, self.population_size)
        best_solution = None
        best_fitness = float('-inf')
        generations_without_improvement = 0
        gen = 0

        for gen in range(self.generations):
            fitness_scores = []
            for individual in population:
                solution, weight = self._evaluate_individual(graph, terminals, individual)
                fitness = -weight if weight < float('inf') else float('-inf')
                fitness_scores.append(fitness)
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_solution = solution
                    generations_without_improvement = 0

            generations_without_improvement += 1
            if generations_without_improvement > 20:
                break
            population = self._evolve(population, fitness_scores, non_terminals, self.mutation_rate)

        if best_solution is None:
            return AlgorithmResult(
                steiner_graph=nx.Graph(), terminals=terminals, steiner_points=set(),
                total_weight=float('inf'), execution_time=time.perf_counter() - start_time,
                algorithm_name=self.name, is_connected=False
            )

        steiner_graph = self._prune_leaves(best_solution, terminals)
        return AlgorithmResult(
            steiner_graph=steiner_graph, terminals=terminals,
            steiner_points=set(steiner_graph.nodes()) - terminals,
            total_weight=self._compute_total_weight(steiner_graph),
            execution_time=time.perf_counter() - start_time,
            algorithm_name=self.name,
            is_connected=self._check_connectivity(steiner_graph, terminals),
            metadata={"generations_run": gen + 1, "final_fitness": best_fitness}
        )

    def _solve_trivial(self, graph, terminals, start_time):
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

    def _initialize_population(self, graph, terminals, non_terminals, pop_size):
        """Initialize population with smarter seeding for disconnected graphs."""
        population = []

        # Find nodes that could connect terminals (on shortest paths)
        connector_nodes = set()
        terminal_list = list(terminals)
        for i, t1 in enumerate(terminal_list[:min(5, len(terminal_list))]):
            for t2 in terminal_list[i+1:min(i+5, len(terminal_list))]:
                try:
                    path = nx.shortest_path(graph, t1, t2, weight='weight')
                    connector_nodes.update(path)
                except nx.NetworkXNoPath:
                    continue

        connector_non_terminals = list(connector_nodes - terminals)

        # Seed population with path-based individuals
        for _ in range(min(pop_size // 4, 10)):
            if connector_non_terminals:
                n = random.randint(0, len(connector_non_terminals))
                individual = set(random.sample(connector_non_terminals, n))
                population.append(individual)

        # Add empty set (might work if terminals directly connected)
        population.append(set())

        # Fill rest with smarter random selection
        max_steiner = min(len(non_terminals), len(terminals) * 2)
        while len(population) < pop_size:
            # Prefer connector nodes with some random additions
            n_connector = random.randint(0, min(max_steiner, len(connector_non_terminals)))
            n_random = random.randint(0, max_steiner // 2)

            individual = set()
            if connector_non_terminals and n_connector > 0:
                individual.update(random.sample(connector_non_terminals, min(n_connector, len(connector_non_terminals))))
            if non_terminals and n_random > 0:
                available = [n for n in non_terminals if n not in individual]
                if available:
                    individual.update(random.sample(available, min(n_random, len(available))))

            population.append(individual)

        return population

    def _evaluate_individual(self, graph, terminals, steiner_points):
        """
        Evaluate an individual by building a Steiner tree.

        Instead of just checking if the subgraph is connected, we:
        1. Build shortest path connections between terminals through steiner points
        2. Use MST on the resulting graph
        """
        nodes = terminals | steiner_points

        # Build a subgraph with shortest paths through the selected nodes
        induced_graph = nx.Graph()

        # Add all selected nodes
        for n in nodes:
            if n in graph.nodes:
                induced_graph.add_node(n, **graph.nodes[n])

        # Add edges that exist between selected nodes
        for u in nodes:
            for v in graph.neighbors(u):
                if v in nodes and not induced_graph.has_edge(u, v):
                    induced_graph.add_edge(u, v, **graph[u][v])

        # Check connectivity
        if induced_graph.number_of_nodes() == 0:
            return nx.Graph(), float('inf')

        if not nx.is_connected(induced_graph):
            # Try to connect using shortest paths through full graph
            # This makes the evaluation smarter
            terminal_list = list(terminals)
            all_edges = set()

            for i, t1 in enumerate(terminal_list):
                for t2 in terminal_list[i+1:]:
                    try:
                        path = nx.shortest_path(graph, t1, t2, weight='weight')
                        # Only use path if it mostly goes through our nodes
                        path_nodes = set(path)
                        if len(path_nodes & nodes) >= len(path_nodes) * 0.5:
                            for j in range(len(path) - 1):
                                all_edges.add((path[j], path[j+1]))
                    except nx.NetworkXNoPath:
                        return nx.Graph(), float('inf')

            if not all_edges:
                return nx.Graph(), float('inf')

            # Build graph from collected edges
            for u, v in all_edges:
                if graph.has_edge(u, v):
                    induced_graph.add_edge(u, v, **graph[u][v])
                    for n in [u, v]:
                        if n not in induced_graph.nodes:
                            induced_graph.add_node(n, **graph.nodes.get(n, {}))

            if not nx.is_connected(induced_graph):
                return nx.Graph(), float('inf')

        try:
            mst = nx.minimum_spanning_tree(induced_graph, weight='weight')
            weight = sum(d.get('weight', 0) for _, _, d in mst.edges(data=True))
            return mst, weight
        except (nx.NetworkXError, ValueError, KeyError):
            return nx.Graph(), float('inf')

    def _evolve(self, population, fitness_scores, non_terminals, mutation_rate):
        n = len(population)
        elite_n = max(1, int(n * self.elite_ratio))
        sorted_indices = np.argsort(fitness_scores)[::-1]
        new_population = [population[sorted_indices[i]].copy() for i in range(elite_n)]
        while len(new_population) < n:
            parent1 = self._tournament_select(population, fitness_scores)
            parent2 = self._tournament_select(population, fitness_scores)
            child = self._crossover(parent1, parent2)
            if random.random() < mutation_rate:
                child = self._mutate(child, non_terminals)
            new_population.append(child)
        return new_population

    def _tournament_select(self, population, fitness_scores, k=3):
        indices = random.sample(range(len(population)), min(k, len(population)))
        best_idx = max(indices, key=lambda i: fitness_scores[i])
        return population[best_idx]

    def _crossover(self, parent1, parent2):
        all_genes = parent1 | parent2
        return {gene for gene in all_genes if random.random() < 0.5}

    def _mutate(self, individual, non_terminals):
        individual = individual.copy()
        if random.random() < 0.5 and individual:
            individual.discard(random.choice(list(individual)))
        else:
            available = set(non_terminals) - individual
            if available:
                individual.add(random.choice(list(available)))
        return individual

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
