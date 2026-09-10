from datetime import datetime
from typing import List, Optional

from beanie import Document
import pymongo
from pymongo import IndexModel


class DownloadScriptEvent(Document):
    """Audit log entry for one download-script generation: who requested it, when,
    which observations/files it covered, and which options were used."""
    username: str
    requested_at: datetime
    obs_ids: List[str]
    obs_names: List[str]
    include_calibration: bool
    file_types: Optional[List[str]] = None
    filenames: List[str]
    file_count: int
    script_username: Optional[str] = None

    class Settings:
        name = "download_script_events"
        indexes = [
            "username",
            IndexModel([("requested_at", pymongo.DESCENDING)]),
        ]
