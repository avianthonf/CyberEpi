import asyncio
from src.db.connection import engine
from src.db.models import Base
import asyncpg

async def check():
    try:
        print("Importing models...")
        print(f"Metadata: {Base.metadata}")
        print("Checking engine...")
        print(f"Engine: {engine}")
        async with engine.connect() as conn:
            print("Connected!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check())
