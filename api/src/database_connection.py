from api.src.models.user import UserInDB


class DatabaseConnection:
    fake_users_db = {
        "johndoe": {
            "username": "johndoe",
            "full_name": "John Doe",
            "email": "johndoe@example.com",
            "hashed_password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
            "disabled": False,
        }
    }

    @staticmethod
    def get_user(username: str):
        if username in DatabaseConnection.fake_users_db:
            user_dict = DatabaseConnection.fake_users_db[username]
            return UserInDB(**user_dict)

