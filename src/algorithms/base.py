"""
Base classes for Steiner Network algorithms.

This module provides the foundation for implementing Steiner tree algorithms:

1. AlgorithmResult - Data container for algorithm outputs
2. SteinerAlgorithm - Abstract base class for all algorithms
3. AlgorithmRegistry - Registry pattern for dynamic algorithm lookup

=== ADDING A NEW ALGORITHM ===

1. Create a new class inheriting from SteinerAlgorithm
2. Set class attributes: name, description, complexity, is_exact
3. Implement the solve() method
4. Decorate with @AlgorithmRegistry.register

Example:
    @AlgorithmRegistry.register
    class MyAlgorithm(SteinerAlgorithm):
        name = "my_algorithm"
        description = "My custom algorithm"
        complexity = "O(n^2)"
        is_exact = False

        def solve(self, graph, terminals, **kwargs):
            # Your implementation here
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Type
import time

import networkx as nx


@dataclass
class AlgorithmResult:
    """Result container for Steiner algorithm execution."""

    # The Steiner tree/network subgraph
    steiner_graph: nx.Graph

    # Terminal nodes that were connected
    terminals: Set[int]

    # Steiner points (non-terminal nodes in the solution)
    steiner_points: Set[int]

    # Total weight/cost of the solution
    total_weight: float

    # Execution time in seconds
    execution_time: float

    # Algorithm name
    algorithm_name: str

    # Whether all terminals are connected
    is_connected: bool

    # Additional algorithm-specific metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate and compute derived attributes."""
        if self.steiner_graph is not None:
            self.node_count = self.steiner_graph.number_of_nodes()
            self.edge_count = self.steiner_graph.number_of_edges()
        else:
            self.node_count = 0
            self.edge_count = 0

    def summary(self) -> Dict[str, Any]:
        """Return a summary dict of the result."""
        return {
            "algorithm": self.algorithm_name,
            "total_weight": self.total_weight,
            "execution_time": self.execution_time,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "terminal_count": len(self.terminals),
            "steiner_point_count": len(self.steiner_points),
            "is_connected": self.is_connected,
            **self.metadata
        }


class SteinerAlgorithm(ABC):
    """Abstract base class for Steiner Network algorithms.

    All algorithms must implement the `solve` method which takes a graph
    and a set of terminal nodes, returning a subgraph that connects all
    terminals with minimum total edge weight.
    """

    # Algorithm metadata
    name: str = "BaseAlgorithm"
    description: str = "Base Steiner algorithm"
    complexity: str = "Unknown"
    is_exact: bool = False

    def __init__(self, **kwargs):
        """Initialize algorithm with optional parameters."""
        self.params = kwargs

    @abstractmethod
    def solve(
        self,
        graph: nx.Graph,
        terminals: Set[int],
        **kwargs
    ) -> AlgorithmResult:
        """
        Find the Steiner tree connecting all terminal nodes.

        Args:
            graph: The full road network graph with 'weight' edge attributes.
            terminals: Set of node IDs that must be connected.
            **kwargs: Additional algorithm-specific parameters.

        Returns:
            AlgorithmResult containing the Steiner subgraph and metadata.
        """
        pass

    def _validate_inputs(self, graph: nx.Graph, terminals: Set[int]) -> None:
        """Validate that inputs are suitable for the algorithm."""
        if graph.number_of_nodes() == 0:
            raise ValueError("Graph is empty")

        if len(terminals) == 0:
            raise ValueError("No terminal nodes provided")

        # Check all terminals exist in graph
        missing = terminals - set(graph.nodes())
        if missing:
            raise ValueError(f"Terminal nodes not in graph: {missing}")

    def _extract_subgraph(
        self,
        graph: nx.Graph,
        edges: List[tuple]
    ) -> nx.Graph:
        """Extract a subgraph from the given edges."""
        subgraph = nx.Graph()

        for u, v in edges:
            if graph.has_edge(u, v):
                edge_data = graph[u][v]
                subgraph.add_edge(u, v, **edge_data)

                # Copy node attributes
                if u not in subgraph.nodes or 'x' not in subgraph.nodes[u]:
                    for attr in ['x', 'y']:
                        if attr in graph.nodes[u]:
                            subgraph.nodes[u][attr] = graph.nodes[u][attr]
                if v not in subgraph.nodes or 'x' not in subgraph.nodes[v]:
                    for attr in ['x', 'y']:
                        if attr in graph.nodes[v]:
                            subgraph.nodes[v][attr] = graph.nodes[v][attr]

        return subgraph

    def _compute_total_weight(self, subgraph: nx.Graph) -> float:
        """Compute total weight of a subgraph."""
        return sum(data.get('weight', 0) for _, _, data in subgraph.edges(data=True))

    def _check_connectivity(self, subgraph: nx.Graph, terminals: Set[int]) -> bool:
        """Check if all terminals are connected in the subgraph."""
        if subgraph.number_of_nodes() == 0:
            return False

        terminals_in_graph = terminals & set(subgraph.nodes())
        if len(terminals_in_graph) != len(terminals):
            return False

        # Check if all terminals are in the same connected component
        terminal_list = list(terminals_in_graph)
        if len(terminal_list) <= 1:
            return True

        first_terminal = terminal_list[0]
        component = nx.node_connected_component(subgraph, first_terminal)
        return all(t in component for t in terminal_list)

    def _timed_solve(
        self,
        solve_func,
        graph: nx.Graph,
        terminals: Set[int],
        **kwargs
    ) -> AlgorithmResult:
        """Wrapper to time the solve function execution."""
        start_time = time.perf_counter()
        result = solve_func(graph, terminals, **kwargs)
        execution_time = time.perf_counter() - start_time

        # Update execution time
        result.execution_time = execution_time
        return result


class AlgorithmRegistry:
    """Registry for Steiner algorithms - allows dynamic registration and lookup."""

    _algorithms: Dict[str, Type[SteinerAlgorithm]] = {}

    @classmethod
    def register(cls, algorithm_class: Type[SteinerAlgorithm]) -> Type[SteinerAlgorithm]:
        """Register an algorithm class (can be used as decorator)."""
        cls._algorithms[algorithm_class.name] = algorithm_class
        return algorithm_class

    @classmethod
    def get(cls, name: str) -> Type[SteinerAlgorithm]:
        """Get algorithm class by name."""
        if name not in cls._algorithms:
            available = list(cls._algorithms.keys())
            raise ValueError(f"Unknown algorithm: {name}. Available: {available}")
        return cls._algorithms[name]

    @classmethod
    def create(cls, name: str, **kwargs) -> SteinerAlgorithm:
        """Create an algorithm instance by name."""
        algorithm_class = cls.get(name)
        return algorithm_class(**kwargs)

    @classmethod
    def list_algorithms(cls) -> List[Dict[str, Any]]:
        """List all registered algorithms with their metadata."""
        return [
            {
                "name": alg.name,
                "description": alg.description,
                "complexity": alg.complexity,
                "is_exact": alg.is_exact,
            }
            for alg in cls._algorithms.values()
        ]

    @classmethod
    def available_names(cls) -> List[str]:
        """Get list of available algorithm names."""
        return list(cls._algorithms.keys())
