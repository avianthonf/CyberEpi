import numpy as np
from typing import List, Dict, Any
from src.dp.mechanisms import vector_gaussian_mechanism

class FedAvgAggregator:
    def __init__(self, model_dim: int, min_clients: int = 10):
        self.model_dim = model_dim
        self.min_clients = min_clients
        self.current_round_gradients = []

    def start_new_round(self):
        self.current_round_gradients = []

    def receive_gradient(self, gradient: np.ndarray):
        """
        Receives a raw gradient update from a client.
        In a real scenario, this would be clipped and noised on the client 
        or securely aggregated. Here we perform server-side DP for demonstration.
        """
        if gradient.shape[0] != self.model_dim:
            raise ValueError(f"Gradient dimension mismatch. Expected {self.model_dim}, got {gradient.shape[0]}")
        self.current_round_gradients.append(gradient)

    def aggregate(self, C: float = 1.0, epsilon: float = 0.5, delta: float = 1e-5) -> np.ndarray:
        """
        Performs FedAvg with Server-side Differential Privacy.
        theta_new = theta_old + (1/K) * sum(DP(clipped(delta_theta_i)))
        """
        K = len(self.current_round_gradients)
        if K < self.min_clients:
            # In production, we'd wait or abort. For now, we aggregate.
            pass
            
        if K == 0:
            return np.zeros(self.model_dim)

        # 1. Clip and noise each gradient
        noised_gradients = []
        for g in self.current_round_gradients:
            g_dp = vector_gaussian_mechanism(g, C, epsilon, delta)
            noised_gradients.append(g_dp)

        # 2. Average
        aggregated_update = np.mean(noised_gradients, axis=0)
        return aggregated_update
