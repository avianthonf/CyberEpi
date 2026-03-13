import redis.asyncio as redis
from typing import Dict, List
from .composition import advanced_composition_bound

class BudgetTracker:
    def __init__(self, redis_client: redis.Redis, max_budget: float = 10.0):
        self.redis = redis_client
        self.max_budget = max_budget

    async def get_remaining(self, user_id: str) -> float:
        key = f"dp_budget:{user_id}"
        val = await self.redis.get(key)
        consumed = float(val) if val else 0.0
        return max(0.0, self.max_budget - consumed)

    async def consume(self, user_id: str, epsilon: float) -> bool:
        """
        Consumes budget for a user. Returns True if successful.
        """
        key = f"dp_budget:{user_id}"
        
        # Use Redis Lua script for atomic check-and-set
        lua_script = """
        local key = KEYS[1]
        local epsilon = tonumber(ARGV[1])
        local max_budget = tonumber(ARGV[2])
        local current = tonumber(redis.call('GET', key) or "0")
        
        if current + epsilon <= max_budget then
            redis.call('SET', key, tostring(current + epsilon))
            return 1
        else
            return 0
        end
        """
        success = await self.redis.eval(lua_script, 1, key, str(epsilon), str(self.max_budget))
        return bool(success)

    async def batch_consume(self, user_ids: List[str], epsilon: float) -> Dict[str, bool]:
        results = {}
        for uid in user_ids:
            results[uid] = await self.consume(uid, epsilon)
        return results

    async def reset(self, user_id: str) -> None:
        key = f"dp_budget:{user_id}"
        await self.redis.delete(key)
