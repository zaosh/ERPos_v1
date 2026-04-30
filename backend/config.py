from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8
    ALGORITHM: str = "HS256"
    BCRYPT_ROUNDS: int = 12
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Storage
    IMAGE_STORAGE_PATH: str = "/data/images"
    IMAGE_BASE_URL: str = "http://localhost:8000/images"

    # CV
    CV_MODEL: str = "openai/clip-vit-base-patch32"
    CV_CONFIDENCE_THRESHOLD: float = 0.4
    CV_PROCESSING_TIMEOUT: float = 5.0

    # Printer
    PRINTER_HOST: str = "192.168.1.100"
    PRINTER_PORT: int = 9100
    PRINTER_TIMEOUT: float = 3.0
    LABEL_WIDTH_MM: int = 57
    LABEL_HEIGHT_MM: int = 32

    # Internal
    TEMP_IMAGE_TTL_SECONDS: int = 600
    PRINT_QUEUE_MAX_ATTEMPTS: int = 5
    BARCODE_PREFIX: str = "THR"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


settings = Settings()
