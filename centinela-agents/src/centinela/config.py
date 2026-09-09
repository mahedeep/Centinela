"""Configuración central de Centinela.

Todos los parámetros se leen del entorno (`.env`). Ningún secreto vive en el
código: `.env.example` documenta cada variable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    # --- OpenAI --------------------------------------------------------------
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-5.6-luna"
    openai_vision_model: str = "gpt-5.6-luna"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_fallback_model: str = "gpt-4o-mini"
    openai_vision_fallback_model: str = "gpt-4o-mini"
    openai_embedding_fallback_model: str = "text-embedding-3-small"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 3

    # --- Modos ---------------------------------------------------------------
    mock_mode: bool = True
    shadow_mode: bool = False

    # --- Umbrales y pesos ----------------------------------------------------
    threshold_review: float = 0.35
    threshold_block: float = 0.70

    w_tx_rules: float = 0.45
    w_tx_similarity: float = 0.25
    w_tx_model: float = 0.30

    w_doc_vision: float = 0.40
    w_doc_checks: float = 0.35
    w_doc_model: float = 0.25

    # --- Documentos ----------------------------------------------------------
    max_upload_mb: int = 10
    max_pdf_pages: int = 5
    pdf_render_dpi: int = 150
    min_image_quality: float = 0.40
    ocr_engine: str = "vision"
    # Metadatos con software de edición o modificación posterior a la emisión
    # ⇒ mínimo `sospechoso`. Desactivable si el canal recibe escaneos legítimos
    # procesados con editores de imagen.
    metadata_warn_gate: bool = True
    trace_retention_days: int = 7

    # --- Persistencia --------------------------------------------------------
    database_url: str = "sqlite:///data/centinela.db"
    data_dir: str = "data"

    # --- API -----------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"
    export_openapi: bool = True

    # --- Precios (USD por 1M de tokens) --------------------------------------
    # NOTA: verificar contra la lista de precios vigente de OpenAI. Los valores
    # por defecto reproducen los supuestos del kit del curso (septiembre 2026).
    price_chat_input_per_1m: float = 0.10
    price_chat_output_per_1m: float = 0.60
    price_embedding_input_per_1m: float = 0.02

    # --- Equipo --------------------------------------------------------------
    team_name: str = "Grupo Centinela"
    team_members: str = ""

    # Límite de tokens de entrada por evaluación (Prompt 01: "evita exceder 1.500").
    max_prompt_tokens: int = Field(default=1500)

    @field_validator("ocr_engine")
    @classmethod
    def _valid_engine(cls, v: str) -> str:
        allowed = {"vision", "tesseract", "mock"}
        if v not in allowed:
            raise ValueError(f"OCR_ENGINE debe ser uno de {sorted(allowed)}")
        return v

    # --- Derivados -----------------------------------------------------------
    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def traces_path(self) -> Path:
        return self.data_path / "traces"

    @property
    def samples_path(self) -> Path:
        return self.data_path / "samples"

    @property
    def sqlalchemy_url(self) -> str:
        """Resuelve rutas SQLite relativas contra la raíz del repositorio."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            raw = self.database_url[len(prefix) :]
            path = Path(raw)
            if not path.is_absolute():
                path = REPO_ROOT / path
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"{prefix}{path}"
        return self.database_url

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key.strip())

    def tx_weights(self) -> tuple[float, float, float]:
        return (self.w_tx_rules, self.w_tx_similarity, self.w_tx_model)

    def doc_weights(self) -> tuple[float, float, float]:
        return (self.w_doc_vision, self.w_doc_checks, self.w_doc_model)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Usado por los tests cuando se cambian variables de entorno en caliente."""
    get_settings.cache_clear()
