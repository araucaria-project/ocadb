from typing import Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from serverish.base.singleton import Singleton

from ocadb.models import document_models


class Connection(Singleton):

    def __init__(self, **kwargs) -> None:
        super().__init__(name = 'MongoConnection', **kwargs)
        self.client = None

    async def ensure_connection(self, connection_string: Optional[str] = None) -> AsyncIOMotorClient:
        if self.client is None:
            self.client = AsyncIOMotorClient(connection_string)
            await init_beanie(
                database=self.client.db_name,
                document_models=document_models,
                allow_index_dropping=True,
            )
        return self.client

