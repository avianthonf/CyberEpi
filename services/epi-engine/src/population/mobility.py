"""Mobility Matrix management and estimation."""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
import h3
from src.db.connection import get_db

class MobilityMatrix:
    def __init__(self, n_patches: int, patch_ids: List[str]):
        self.n_patches = n_patches
        self.patch_ids = patch_ids
        self.patch_to_idx = {pid: i for i, pid in enumerate(patch_ids)}
        self.M = np.eye(n_patches) # Default: no movement

    def validate(self) -> bool:
        """Assert row sums <= 1.0 (some people might leave the study area) and non-negative."""
        assert np.all(self.M >= 0), "Mobility elements must be non-negative"
        row_sums = np.sum(self.M, axis=1)
        assert np.all(row_sums <= 1.0001), "Row sums must be <= 1.0"
        return True

    async def load_from_db(self, region_id: str) -> None:
        """Load mobility fractions from database."""
        async for db in get_db():
            # mobility_matrix table schema: from_patch, to_patch, fraction
            # We need to find the table name from Task 6: mobility_matrix
            query = sa.text("SELECT from_patch, to_patch, fraction FROM mobility_matrix WHERE region_id = :rid")
            result = await db.execute(query, {"rid": region_id})
            rows = result.all()
            
            # Reset M
            self.M = np.zeros((self.n_patches, self.n_patches))
            
            # Note: We need to decide what happens to people not accounted for in M.
            # Usually people who STAY in patch i: M[i,i] = 1 - sum_{j!=i} M[i,j]
            # The matrix in DB might only store EXCHANGES.
            
            # Assume DB stores all non-zero entries or we manually fill diagonals.
            for from_p, to_p, fraction in rows:
                if from_p in self.patch_to_idx and to_p in self.patch_to_idx:
                    self.M[self.patch_to_idx[from_p], self.patch_to_idx[to_p]] = fraction
            
            # Ensure diagonal is set if not present (simplified: people who don't travel stay)
            for i in range(self.n_patches):
                row_sum_others = np.sum(self.M[i, :]) - self.M[i, i]
                self.M[i, i] = 1.0 - row_sum_others
            
            self.validate()
            break # Exit after one db session

    def load_from_csv(self, file_path: str) -> None:
        """Load from authority upload CSV."""
        df = pd.read_csv(file_path)
        # Expected columns: from_patch_id, to_patch_id, fraction
        self.M = np.zeros((self.n_patches, self.n_patches))
        
        for _, row in df.iterrows():
            f = str(row['from_patch_id'])
            t = str(row['to_patch_id'])
            frac = float(row['fraction'])
            if f in self.patch_to_idx and t in self.patch_to_idx:
                self.M[self.patch_to_idx[f], self.patch_to_idx[t]] = frac
                
        for i in range(self.n_patches):
            row_sum_others = np.sum(self.M[i, :]) - self.M[i, i]
            self.M[i, i] = 1.0 - row_sum_others
            
        self.validate()

    def estimate_from_gravity_model(self, patch_pops: Dict[str, float], patch_coords: Dict[str, Tuple[float, float]]) -> np.ndarray:
        """
        Gravity model: M[i,j] proportional to (pop_i * pop_j) / dist(i,j)^2
        Used as fallback.
        """
        self.M = np.zeros((self.n_patches, self.n_patches))
        
        for i, pid_i in enumerate(self.patch_ids):
            pop_i = patch_pops[pid_i]
            coord_i = patch_coords[pid_i]
            
            total_out_weight = 0.0
            for j, pid_j in enumerate(self.patch_ids):
                if i == j:
                    continue
                
                pop_j = patch_pops[pid_j]
                coord_j = patch_coords[pid_j]
                
                # Haversine distance
                dist = h3.point_dist(coord_i, coord_j, unit='km')
                if dist < 0.1:
                    dist = 0.1 # Min distance
                
                weight = (pop_i * pop_j) / (dist ** 2)
                self.M[i, j] = weight
                total_out_weight += weight
            
            # Normalize so that say 10% of people are traveling (parameterized or assumed)
            mobility_fraction = 0.1 # 10% movement
            if total_out_weight > 0:
                self.M[i, :] = (self.M[i, :] / total_out_weight) * mobility_fraction
                self.M[i, i] = 1.0 - mobility_fraction
            else:
                self.M[i, i] = 1.0
                
        self.validate()
        return self.M
