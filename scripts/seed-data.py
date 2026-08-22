"""Seed baseline EpiParams for the three demo regions.

Idempotent: re-running updates rows in place (region_id is unique), so this
is safe to run on every environment bootstrap.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "epi-engine"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.db.models import EpiParams

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://cyberepi:devpassword@127.0.0.1:5432/cyberepi"
)

BASELINE = {
    "source": "manual_override",
    "beta": 0.6,
    "sigma": 0.25,
    "gamma": 0.1,
    "rho": 0.5,
    "fA": 0.3,
    "fM": 0.5,
    "fS": 0.2,
    "alpha": 0.1,
    "h_rate": 0.05,
    "delta": 0.02,
    "mu": 0.01,
    "mu_icu": 0.05,
    "gamma_A": 0.1,
    "gamma_M": 0.1,
    "gamma_S": 0.1,
    "gamma_H": 0.1,
    "gamma_ICU": 0.1,
    "papp": 0.12,
    "N_pop": 1000000,
}

REGIONS = ["region-a", "region-b", "region-c"]


async def seed() -> None:
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        for rid in REGIONS:
            existing = (
                await session.execute(select(EpiParams).where(EpiParams.region_id == rid))
            ).scalar_one_or_none()
            if existing is None:
                session.add(EpiParams(id=uuid.uuid4(), region_id=rid, **BASELINE))
                print(f"Seeded {rid}")
            else:
                for key, value in BASELINE.items():
                    setattr(existing, key, value)
                print(f"Updated {rid}")
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
