"""Runtime configuration loaded from environment variables.

All variables are supplied by app.yaml in production.
Local dev falls back to ~/.databrickscfg defaults so the app boots for smoke tests.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Unity Catalog
    catalog: str = Field(default="horizontal_finance_dev", validation_alias="DATABRICKS_CATALOG")
    silver_schema: str = Field(default="silver", validation_alias="DATABRICKS_SILVER_SCHEMA")
    gold_schema: str = Field(default="gold", validation_alias="DATABRICKS_GOLD_SCHEMA")
    ml_schema: str = Field(default="ml", validation_alias="DATABRICKS_ML_SCHEMA")

    # SQL warehouse (OBO target) — resource binding sets this from app.yaml
    warehouse_id: str = Field(default="", validation_alias="DATABRICKS_WAREHOUSE_ID")

    # Databricks host — auto-set inside Apps; set DATABRICKS_HOST locally
    databricks_host: str = Field(default="", validation_alias="DATABRICKS_HOST")

    # Helios Spend Analytics Genie Space ID — used by the ask_genie chatbot tool
    genie_space_id: str = Field(default="", validation_alias="GENIE_SPACE_ID")

    # SP M2M credentials — saved under APP_SP_* names before CLIENT_ID/SECRET
    # are cleared at startup. Used by the chatbot to get an M2M token for FMAPI.
    sp_client_id: str = Field(default="", validation_alias="APP_SP_CLIENT_ID")
    sp_client_secret: str = Field(default="", validation_alias="APP_SP_CLIENT_SECRET")

    # FMAPI / Model Serving endpoint name for the chatbot
    serving_endpoint_name: str = Field(
        default="databricks-meta-llama-3-3-70b-instruct",
        validation_alias="DATABRICKS_SERVING_ENDPOINT_NAME",
    )

    # Lakebase Postgres
    lakebase_host: str = Field(default="", validation_alias="LAKEBASE_HOST")
    lakebase_port: int = Field(default=5432, validation_alias="LAKEBASE_PORT")
    lakebase_database: str = Field(default="databricks_postgres", validation_alias="LAKEBASE_DATABASE")
    # Full resource path for OAuth credential generation
    lakebase_endpoint: str = Field(
        default="projects/helios-sourcing/branches/production/endpoints/primary",
        validation_alias="LAKEBASE_ENDPOINT",
    )

    # Local-dev affordances
    dev_allow_anonymous: bool = Field(
        default=False, validation_alias="APP_DEV_ALLOW_ANONYMOUS"
    )
    dev_user_email: str = Field(
        default="local-dev@example.com", validation_alias="APP_DEV_USER_EMAIL"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def gold(self) -> str:
        return f"{self.catalog}.{self.gold_schema}"

    @property
    def silver(self) -> str:
        return f"{self.catalog}.{self.silver_schema}"

    @property
    def ml(self) -> str:
        return f"{self.catalog}.{self.ml_schema}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
