from src.models import Reward
from src.pkg.db import DbContext


class RewardsRepo(DbContext):
    async def get_rewards(self) -> list[Reward]:
        query = """
            SELECT
                id as reward_id,
                name,
                cost
            FROM rewards;
        """
        rows = await self.pool.fetch(query)
        return [Reward(**row) for row in rows]

    async def get_reward_by_id(self, task_id: int) -> Reward:
        query = """
            SELECT
                id as reward_id,
                name,
                cost
            FROM rewards
            WHERE id = $1;
        """
        row = await self.pool.fetchrow(query, task_id)
        return Reward(**row)
