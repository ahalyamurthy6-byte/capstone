import asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from common.config import get_settings
from common.db import fetch_all

url = get_settings().DATABASE_URL
print("DATABASE_URL =", url)

async def main():
    async with AsyncPostgresSaver.from_conn_string(url) as s:
        await s.setup()

asyncio.run(main())
print(fetch_all("select current_database() db, inet_server_port() port", None))
print(fetch_all("select table_name from information_schema.tables where table_name like 'checkpoint'", None))
