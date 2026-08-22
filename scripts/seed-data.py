import asyncio
import uuid
import os
import sys
sys.path.insert(0, "/home/avinash/Projects/CyberEpi/services/epi-engine")
from src.db.models import EpiParams
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://cyberepi:devpassword@127.0.0.1:5432/cyberepi")

async def seed():
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    
    regions = ["region-a", "region-b", "region-c"]
    
    async with factory() as session:
        for rid in regions:
            params = EpiParams(
                id=uuid.uuid4(),
                region_id=rid,
                source="manual_override",
                beta=0.6,
                sigma=0.25,
                gamma=0.1,
                rho=0.5,
                fA=0.3,
                fM=0.5,
                fS=0.2,
                alpha=0.1,
                h_rate=0.05,
                delta=0.02,
                mu=0.01,
                mu_icu=0.05,
                gamma_A=0.1,
                gamma_M=0.1,
                gamma_S=0.1,
                gamma_H=0.1,
                gamma_ICU=0.1,
                papp=0.12,
                N_pop=1000000,
            )
            session.add(params)
            print(f"Seeded {rid}")
        await session.commit()
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed())
