import logging
from typing import Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from serverish.base.singleton import Singleton

from ocadb.models import document_models

log = logging.getLogger(__name__.rsplit('.')[-1])

class Connection(Singleton):

    def __init__(self, **kwargs) -> None:
        super().__init__(name = 'MongoConnection', **kwargs)
        self.client = None

    async def ensure_connection(self,
                                connection_string: Optional[str] = None,
                                database_name:str = 'ocadb'
                                ) -> AsyncIOMotorClient:
        if self.client is None:
            self.client = AsyncIOMotorClient(connection_string)
            self.database = self.client[database_name]
            try:
                await init_beanie(
                    database=self.database,
                    document_models=document_models,
                    allow_index_dropping=True,
                )
            except ConnectionFailure as e:
                log.error(f"Failed to connect to {self.client.db_name}: {e}")
                raise e
            log.info(f"Connected to {self.client.db_name}")
        return self.client

