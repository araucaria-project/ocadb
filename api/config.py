from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix='ocadb.')

    # administration information
    app_name: str = "ocadb_api"
    admin_email: str = ""

    # server settings
    host: str = "0.0.0.0"
    port: int = 8084
    reload: bool = True
    workers: int = 2

