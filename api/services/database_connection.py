from ocadb.models import UserInDB


class DatabaseConnection:
    @staticmethod
    async def get_user(username: str):
        """Get user from MongoDB database"""
        return await UserInDB.find_one(UserInDB.username == username)
    
    @staticmethod
    async def create_user(username: str, email: str, full_name: str, hashed_password: str, disabled: bool = False, access_tags: list[str] = []):
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

