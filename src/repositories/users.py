from src.pkg.db import DbContext


class UsersRepo(DbContext):
    async def update_balance(self, tg_id: int, amount: int) -> None:
        query = """
            UPDATE users SET balance = $1 WHERE tg_id = $2
        """
        await self.pool.execute(query, amount, tg_id)

    async def spend_points(self, tg_id: int, amount: int) -> int | None:
        """Списывает amount и возвращает новый баланс.

        Возвращает None, если средств не хватает (или пользователя нет),
        при этом баланс не меняется — проверка и списание идут одним запросом.
        """
        query = """
            UPDATE users
            SET balance = balance - $1
            WHERE tg_id = $2 AND balance >= $1
            RETURNING balance
        """
        return await self.pool.fetchval(query, amount, tg_id)

    async def get_balance(self, tg_id: int) -> int:
        query = """
            SELECT balance FROM users WHERE tg_id = $1
        """
        return await self.pool.fetchval(query, tg_id)
