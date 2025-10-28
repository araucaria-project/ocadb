from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # secrets
    JWT_SECRET_KEY: str = "fallback-secret-key-for-development-only"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: str = "30"

    # administration information
    app_name: str = "ocadb_api"
    admin_email: str = ""

    # application settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "ocadb"
    MONGODB_USER: str = "user"
    MONGODB_PASS: str = "pass"

    # server settings
    host: str = "0.0.0.0"
    port: int = 8084
    reload: bool = True
    workers: int = 2

    # s3 settings
    S3_KEY_ID: str = "this-is-2137-keys"
    S3_SECRET: str = "this-is-a-vatican-secret"
    S3_REGION: str = "eu-central-003"
    ENDPOINT: str = "https://s3.eu-central-003.backblazeb2.com"
    BUCKET_NAME: str = "bucket-test-s3"

    # .env file config
    model_config = SettingsConfigDict(env_file=".env", env_prefix='ocadb.')