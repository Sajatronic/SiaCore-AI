from pathlib import Path

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_DASHSCOPE_MODEL = "qwen-plus"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_CEREBRAS_MODEL = "gemma-4-31b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[
            Path(__file__).resolve().parent.parent / ".env",
            ".env"
        ],
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    gdelt_api_key: str = ""
    marketaux_api_token: str = ""
    gnews_api_token: str = ""
    newsdata_api_key: str = ""

    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GROQ_API_KEY",
        ),
    )
    llm_provider: str = Field(
        default="openai_compatible",
        validation_alias=AliasChoices("LLM_PROVIDER", "LLM_BACKEND"),
    )
    cerebras_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CEREBRAS_API_KEY"),
    )
    cerebras_model: str = Field(
        default=DEFAULT_CEREBRAS_MODEL,
        validation_alias=AliasChoices("CEREBRAS_MODEL"),
    )
    cerebras_reasoning_effort: str = Field(
        default="medium",
        validation_alias=AliasChoices("CEREBRAS_REASONING_EFFORT"),
    )
    cerebras_top_p: float = Field(
        default=1.0,
        validation_alias=AliasChoices("CEREBRAS_TOP_P"),
    )
    openrouter_model: str = Field(
        default=DEFAULT_GROQ_MODEL,
        validation_alias=AliasChoices("OPENROUTER_MODEL", "GEMINI_MODEL", "GROQ_MODEL"),
    )
    openrouter_base_url: str = Field(
        default=DEFAULT_GROQ_BASE_URL,
        validation_alias=AliasChoices(
            "OPENROUTER_BASE_URL",
            "LLM_API_BASE_URL",
            "GEMINI_BASE_URL",
            "GROQ_BASE_URL",
        ),
    )

    @field_validator(
        "openrouter_api_key",
        "openrouter_model",
        "openrouter_base_url",
        "cerebras_api_key",
        "cerebras_model",
        "llm_provider",
        mode="before",
    )
    @classmethod
    def _strip_env_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().strip('"').strip("'")
        return value

    @model_validator(mode="after")
    def _normalize_llm_settings(self) -> "Settings":
        """Auto-fix common misconfigurations (URL in model field, OpenRouter model IDs)."""
        model = self.openrouter_model
        if model.startswith("http://") or model.startswith("https://"):
            self.openrouter_base_url = model.rstrip("/")
            if "dashscope" in model or "aliyuncs" in model:
                self.openrouter_model = DEFAULT_DASHSCOPE_MODEL
            elif "generativelanguage.googleapis.com" in model:
                self.openrouter_model = DEFAULT_GEMINI_MODEL
            elif "groq.com" in model:
                self.openrouter_model = DEFAULT_GROQ_MODEL
            else:
                self.openrouter_model = "google/gemini-2.5-flash"

        if "generativelanguage.googleapis.com" in self.openrouter_base_url:
            if self.openrouter_model.startswith("google/"):
                self.openrouter_model = self.openrouter_model.split("/", 1)[1]

        return self

    @property
    def llm_base_url(self) -> str:
        return self.openrouter_base_url.rstrip("/")

    @property
    def uses_cerebras(self) -> bool:
        return self.llm_provider.strip().lower() == "cerebras"

    # Supabase Postgres connection string, e.g.
    #   postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
    # Get it from Supabase -> Connect -> ORM tab. Accepts either env var name
    # below (Supabase's default is DATABASE_URL; DB_CONNECTION_STRING also works).
    # Do NOT include a `?pgbouncer=true` suffix -- that's Prisma-specific and
    # will make psycopg2 reject the connection.
    db_connection_string: str = Field(
        default="",
        validation_alias=AliasChoices("DB_CONNECTION_STRING", "DATABASE_URL"),
    )

    # Supabase REST API (PostgREST) credentials -- used instead of a direct
    # Postgres connection when ports 5432/6543 are blocked by the network.
    # Get these from Supabase -> Project Settings -> API.
    # SUPABASE_KEY should be the service_role key (server-side use only).
    supabase_url: str = ""
    supabase_key: str = ""

    pipeline_version: str = "0.5.0"
    data_root: Path | None = None
    canonical_entities_path: Path = Path("data/canonical_entities.json")
    classification_confidence_threshold: float = 0.6
    entity_link_confidence_threshold: float = 0.7
    hitl_review_queue_path: Path = Path("data/review_queue.json")
    prefilter_drops_path: Path = Path("data/prefilter_drops.json")
    relevance_min_score: float = 0.40
    alert_rules_path: Path = Path("config/alert_rules.yaml")
    persist_events: bool = True
    persist_require_db: bool = False
    persist_fallback_postgres: bool = False

    risk_analysis_enabled: bool = True
    risk_analysis_min_severity: float = 50.0
    risk_analysis_min_confidence: float = 0.5
    risk_analysis_priority_severity: float = 65.0
    risk_analysis_max_events: int = 0

    impact_prediction_enabled: bool = True
    impact_prediction_min_severity: float = 35.0
    impact_prediction_llm_refine: bool = True
    impact_prediction_max_llm_refines: int = 10
    impact_baselines_path: Path = Path("config/impact_baselines.yaml")
    default_lead_time_days: int = 21

    enabled_providers: list[str] = ["gdelt", "gdacs", "marketaux", "gnews", "newsdata"]

    supply_chain_search_query: str = (
        "semiconductor OR supply chain OR factory shutdown OR sanctions OR port closure OR strike"
    )
    provider_fetch_limit: int = 25
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3

    llm_max_retries: int = 4
    llm_max_concurrent: int = 1
    llm_parallel_workers: int = 1
    llm_min_request_interval_seconds: float = 2.0
    llm_entity_linking_enabled: bool = True
    llm_entity_linking_mode: str = "auto"
    llm_linking_max_article_chars: int = 2500
    catalog_inference_max_components: int = 100

    siaeye_result_json_path: Path = Path("result.json")
    siaeye_api_host: str = "0.0.0.0"
    siaeye_api_port: int = 8000
    siaeye_cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
        ]
    )
    siaeye_frontend_dist: Path = Path("frontend/dist")

    @property
    def effective_llm_entity_linking_mode(self) -> str:
        """auto → fuzzy_first on Groq (TPM limits), always elsewhere."""
        mode = self.llm_entity_linking_mode.strip().lower()
        if mode != "auto":
            return mode
        if self.uses_cerebras:
            return "always"
        if "groq.com" in self.llm_base_url:
            return "fuzzy_first"
        return "always"

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def resolved_data_root(self) -> Path:
        if self.data_root is not None:
            return self.data_root.resolve()
        return self.project_root.parent


settings = Settings()