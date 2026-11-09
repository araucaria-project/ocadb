import logging
import re

from ocadb.models import UserInDB
from ocadb.models.user import normalize_email

log = logging.getLogger(__name__)


class DatabaseConnection:
    @staticmethod
    async def get_user(username: str):
        """Get user from MongoDB database"""
        return await UserInDB.find_one(UserInDB.username == username)

    @staticmethod
    async def get_user_by_identifier(identifier: str) -> UserInDB | None:
        """Find a user by Araucaria ID (username) or, if it contains '@', by email."""
        identifier = identifier.strip()
        if "@" not in identifier:
            return await DatabaseConnection.get_user(identifier)
        email = normalize_email(identifier)
        if email is None:
            return None
        # Case-insensitive, so emails stored before normalization still match.
        users = await UserInDB.find(
            {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}
        ).limit(2).to_list()
        if len(users) > 1:
            log.warning("Email %s matches several users; refusing to pick one", email)
            return None
        return users[0] if users else None

    @staticmethod
    async def create_user(username: str, email: str | None, full_name: str, hashed_password: str | None, disabled: bool = False, access_tags: list[str] = []):
        """Create a new user in MongoDB database"""
        user = UserInDB(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            disabled=disabled,
            access_tags=access_tags
        )
        await user.insert()
        return user
