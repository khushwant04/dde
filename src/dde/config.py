"""Runtime configuration loaded exclusively from environment variables."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from dde.errors import ProviderConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    model: str | None = Field(default=None, alias="DDE_MODEL")
    auth_mode: Literal["api_key", "azure_identity"] = Field(
        default="api_key", alias="DDE_AUTH_MODE"
    )
    max_file_bytes: int = Field(default=15_728_640, ge=1, alias="DDE_MAX_FILE_BYTES")
    max_pages: int = Field(default=10, ge=1, le=100, alias="DDE_MAX_PAGES")
    max_image_pixels: int = Field(default=25_000_000, ge=1, alias="DDE_MAX_IMAGE_PIXELS")
    max_tabular_rows: int = Field(default=10_000, ge=1, le=1_000_000, alias="DDE_MAX_TABULAR_ROWS")
    max_tabular_columns: int = Field(default=100, ge=1, le=10_000, alias="DDE_MAX_TABULAR_COLUMNS")
    max_cell_chars: int = Field(default=4_096, ge=1, alias="DDE_MAX_CELL_CHARS")
    max_tabular_chars: int = Field(default=200_000, ge=1, alias="DDE_MAX_TABULAR_CHARS")
    max_sheets: int = Field(default=20, ge=1, le=1_000, alias="DDE_MAX_SHEETS")
    max_xlsx_zip_entries: int = Field(
        default=1_000, ge=1, le=100_000, alias="DDE_MAX_XLSX_ZIP_ENTRIES"
    )
    max_xlsx_uncompressed_bytes: int = Field(
        default=52_428_800, ge=1, alias="DDE_MAX_XLSX_UNCOMPRESSED_BYTES"
    )
    render_dpi: int = Field(default=144, ge=72, le=300, alias="DDE_RENDER_DPI")
    request_timeout_seconds: float = Field(
        default=120.0, gt=0, le=600, alias="DDE_REQUEST_TIMEOUT_SECONDS"
    )
    max_request_bytes: int = Field(default=16_777_216, ge=1, alias="DDE_MAX_REQUEST_BYTES")
    max_concurrent_requests: int = Field(
        default=2, ge=1, le=128, alias="DDE_MAX_CONCURRENT_REQUESTS"
    )
    api_timeout_seconds: float = Field(default=130.0, gt=0, le=900, alias="DDE_API_TIMEOUT_SECONDS")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", alias="DDE_LOG_LEVEL"
    )

    def require_provider(self) -> None:
        missing: list[str] = []
        if not self.openai_base_url:
            missing.append("OPENAI_BASE_URL")
        if not self.model:
            missing.append("DDE_MODEL")
        if self.auth_mode == "api_key" and self.openai_api_key is None:
            missing.append("OPENAI_API_KEY")
        if missing:
            raise ProviderConfigurationError(
                "Missing provider configuration: " + ", ".join(missing)
            )

    def safe_summary(self) -> dict[str, object]:
        return {
            "base_url_configured": bool(self.openai_base_url),
            "model": self.model,
            "auth_mode": self.auth_mode,
            "credential_configured": self.auth_mode == "azure_identity"
            or self.openai_api_key is not None,
            "max_file_bytes": self.max_file_bytes,
            "max_pages": self.max_pages,
            "max_image_pixels": self.max_image_pixels,
            "max_tabular_rows": self.max_tabular_rows,
            "max_tabular_columns": self.max_tabular_columns,
            "max_cell_chars": self.max_cell_chars,
            "max_tabular_chars": self.max_tabular_chars,
            "max_sheets": self.max_sheets,
            "max_xlsx_zip_entries": self.max_xlsx_zip_entries,
            "max_xlsx_uncompressed_bytes": self.max_xlsx_uncompressed_bytes,
            "render_dpi": self.render_dpi,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_request_bytes": self.max_request_bytes,
            "max_concurrent_requests": self.max_concurrent_requests,
            "api_timeout_seconds": self.api_timeout_seconds,
        }
