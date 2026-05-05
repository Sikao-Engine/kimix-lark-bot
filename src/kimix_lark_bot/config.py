# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

_VALID_LLM_PROVIDERS = frozenset(
    ["moonshot", "openai", "google", "deepseek", "anthropic"]
)


class AgentConfig(BaseModel):
    """Bot configuration with validation."""

    app_id: str = ""
    app_secret: str = ""
    projects: list[dict[str, str]] = Field(default_factory=list)
    cli_tool: str = "opencode-cli"
    base_port: int = Field(default=4096, ge=1024, le=65535)
    max_sessions: int = Field(default=10, ge=1, le=50)
    callback_timeout: int = 300
    auto_restart: bool = False
    llm_provider: str | None = None
    llm_api_key: str | None = None
    admin_chat_id: str | None = None
    default_chat_id: str | None = None
    config_path: str | None = None

    @field_validator(
        "llm_provider", "llm_api_key", "admin_chat_id", "default_chat_id", mode="before"
    )
    @classmethod
    def _empty_to_none(cls, v: object) -> str | None:
        return v if v else None

    @field_validator("projects", mode="before")
    @classmethod
    def _filter_projects(cls, v: object) -> list[dict[str, str]]:
        if not isinstance(v, list):
            return []
        return [
            {
                "slug": str(p.get("slug", "")),
                "path": str(p.get("path", "")),
                "label": str(p.get("label", "")),
            }
            for p in v
            if isinstance(p, dict) and p.get("path")
        ]

    def validate(self) -> list[str]:
        """Return list of validation warnings (empty = all good)."""
        warnings: list[str] = []
        if not self.app_id:
            warnings.append("app_id is empty - Feishu connection will fail")
        if not self.app_secret:
            warnings.append("app_secret is empty - Feishu connection will fail")
        if self.llm_provider and self.llm_provider not in _VALID_LLM_PROVIDERS:
            warnings.append(
                f"Unknown llm_provider: {self.llm_provider} (valid: {', '.join(_VALID_LLM_PROVIDERS)})"
            )
        for p in self.projects:
            path = p.get("path", "")
            if path:
                try:
                    resolved = Path(path).expanduser()
                    if not resolved.exists():
                        warnings.append(f"Project path does not exist: {path}")
                except Exception:
                    warnings.append(f"Invalid project path: {path}")
        return warnings


def load_config(config_path: str) -> AgentConfig:
    p = Path(config_path)
    data: dict = {}
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.error("Failed to read config %s: %s", config_path, exc)

    try:
        config = AgentConfig(config_path=config_path, **data)
    except ValidationError as exc:
        logger.error("Failed to parse config %s: %s", config_path, exc)
        config = AgentConfig(config_path=config_path)

    for w in config.validate():
        logger.warning("Config: %s", w)
    return config


def create_default_config(config_path: str) -> None:
    p = Path(config_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    config = AgentConfig(
        projects=[
            {"slug": "sailzen", "path": "~/repos/SailZen", "label": "SailZen"}
        ]
    )

    header = """\
# Feishu Agent Bridge Configuration
# Usage: uv run bot/feishu_agent.py -c bot/opencode.bot.yaml

# Feishu App Credentials (Required)
# Get from: https://open.feishu.cn/app
"""
    footer = """\
# Optional: LLM settings for intent understanding
# If not set, falls back to environment variables (MOONSHOT_API_KEY, etc.)
# Supported providers: moonshot, openai, google, deepseek, anthropic
# llm_provider: "moonshot"
# llm_api_key: "your-api-key-here"

# Optional: Admin notification settings
# admin_chat_id: "oc_xxxxxxxxxxxxxxxx"  # 管理员的chat_id，用于接收启动/关闭通知

# Optional: Default chat for proactive messages
# default_chat_id: "oc_xxxxxxxxxxxxxxxx"  # 默认chat_id，用于机器人主动发送消息
"""
    payload = config.model_dump(
        exclude={"config_path"},
        exclude_none=True,
    )
    yaml_body = yaml.dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )

    with open(p, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n")
        f.write(yaml_body)
        f.write(footer)
    print(f"Created config: {config_path}")
    print("Please edit and add your Feishu credentials.")
