from src.models import Task
from src.pkg.db import DbContext


class TasksRepo(DbContext):
    async def get_tasks(self) -> list[Task]:
        query = """
            SELECT
                id as task_id,
                text,
                completed,
                reward_points
            FROM tasks;
        """
        rows = await self.pool.fetch(query)
        return [Task(**row) for row in rows]

    async def get_task_by_id(self, task_id: int) -> Task:
        query = """
            SELECT
                id as task_id,
                text,
                completed,
                reward_points
            FROM tasks
            WHERE id = $1;
        """
        row = await self.pool.fetchrow(query, task_id)
        return Task(**row)
