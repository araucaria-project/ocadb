import bcrypt

class CryptoService:

    @staticmethod
    def verify_password(plain_password, hashed_password):
        password_byte_enc = plain_password.encode('utf-8')
        hashed_pwd = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_byte_enc, hashed_pwd)

    @staticmethod
    def get_password_hash(password):
        pwd_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed_pwd = bcrypt.hashpw(pwd_bytes, salt)
        string_pwd = hashed_pwd.decode('utf-8')
        return string_pwd
