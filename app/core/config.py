from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_port: int = 8000
    secret_key: str = "dev-secret-change-in-prod"
    database_url: str = "sqlite:///./social_ultimate.db"

    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    experimental_enabled: bool = False
    experimental_require_explicit_opt_in: bool = True

    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_redirect_uri: str = "http://localhost:8000/api/instagram/oauth/callback"

    chromedriver_path: str = ""
    proxy_service_url: str = ""

    fakemail_domain: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()