from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "Novel Signal API"
    api_v1_prefix: str = "/api/v1"
    internal_auth_secret: SecretStr = SecretStr("change-me")
    dashboard_access_code: SecretStr = SecretStr("")
    dashboard_auth_cookie: str = "novel_signal_dashboard"
    cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://novel_signal:novel_signal@localhost:5432/novel_signal"
    redis_url: str = "redis://localhost:6379/0"
    object_store_endpoint: str = "http://localhost:9000"
    object_store_bucket: str = "novel-signal-raw"
    object_store_access_key: SecretStr = SecretStr("novel_signal")
    object_store_secret_key: SecretStr = SecretStr("novel_signal_dev")
    object_store_region: str = "ap-south-1"
    raw_evidence_signing_ttl_seconds: int = 900
    amazon_in_concurrency: int = 1
    amazon_in_min_delay_seconds: int = 8
    amazon_in_max_delay_seconds: int = 15
    amazon_in_geo_code: str = "IN"
    amazon_in_pincode: str = ""
    amazon_in_location_label: str = ""
    amazon_in_device_profile: str = "desktop"
    google_serp_concurrency: int = 1
    google_serp_min_delay_seconds: int = 8
    google_serp_geo_code: str = "IN"
    google_serp_device_profile: str = "desktop"
    google_serp_locale: str = "en-IN"
    google_serp_timezone_id: str = "Asia/Kolkata"
    google_serp_novel_domains: str = ""
    google_serp_competitor_domains: str = ""
    collector_timeout_seconds: int = 45
    collector_max_attempts: int = 3
    collector_failure_rate_warn_threshold: float = 0.05
    collector_freshness_warn_minutes: int = 60
    collector_completeness_warn_ratio: float = 0.98
    raw_evidence_retention_days: int = 90
    collection_health_window_hours: int = 24
    amazon_lwa_client_id: str = ""
    amazon_lwa_client_secret: SecretStr = SecretStr("")
    amazon_lwa_refresh_token: SecretStr = SecretStr("")
    amazon_aws_access_key_id: str = ""
    amazon_aws_secret_access_key: SecretStr = SecretStr("")
    amazon_role_arn: str = ""
    amazon_region: str = "eu-west-1"
    amazon_marketplace_id: str = "A21TJRUUN4KGV"
    amazon_ads_client_id: str = ""
    amazon_ads_client_secret: SecretStr = SecretStr("")
    amazon_ads_refresh_token: SecretStr = SecretStr("")
    amazon_ads_profile_ids: str = ""
    google_search_console_credentials_json: SecretStr = SecretStr("")
    google_search_console_sites: str = ""
    meta_app_id: str = ""
    meta_app_secret: SecretStr = SecretStr("")
    meta_access_token: SecretStr = SecretStr("")
    meta_ad_account_ids: str = ""
    meta_ad_library_access_token: SecretStr = SecretStr("")

    @field_validator("database_url", mode="after")
    @classmethod
    def use_installed_postgres_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
