from passlib.context import CryptContext


class CryptoService:
    PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")

    @staticmethod
    def verify_password(plain_password, hashed_password):
        return CryptoService.PWD_CONTEXT.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password):
        return CryptoService.PWD_CONTEXT.hash(password)
