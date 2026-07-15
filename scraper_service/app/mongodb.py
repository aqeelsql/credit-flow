from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import Settings


class MongoState:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        if self.client is not None:
            return
        self.client = AsyncIOMotorClient(self.settings.mongodb_url)
        self.db = self.client[self.settings.mongodb_database]
        await self.db.command("ping")
        await self.ensure_indexes()

    async def ensure_indexes(self) -> None:
        if self.db is None:
            return
        await self.db[self.settings.mongodb_collection].create_index("event_id", unique=True, sparse=True)
        await self.db[self.settings.mongodb_collection].create_index([("account_id", 1), ("created_at", -1)])
        await self.db.processed_events.create_index("event_id", unique=True)
        await self.db.domain_rate_limits.create_index("domain", unique=True)
        await self.db.recurring_scrapes.create_index("next_run_at")
        await self.db.research_jobs.create_index([("account_id", 1), ("created_at", -1)])
        await self.db.research_jobs.create_index("next_run_at")
        await self.db.research_packs.create_index([("account_id", 1), ("created_at", -1)])

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()
        self.client = None
        self.db = None

    async def ping(self) -> bool:
        try:
            await self.connect()
            if self.db is not None:
                await self.db.command("ping")
            return True
        except Exception:
            return False
