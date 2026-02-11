from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SQLSERVER_CONN_STRING: str = ""
    MODEL_DIR: str = "./models"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
