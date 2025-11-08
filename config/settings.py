"""Configuration management using Pydantic Settings and environment variables."""

import os
from pathlib import Path
from typing import List, Literal, Optional
import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from models.schemas import CategoryDefinition, ClassificationConfig


def get_config_dir() -> Path:
    """Get the configuration directory (~/.mail-agent)."""
    config_dir = Path.home() / ".mail-agent"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI Configuration
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="""OpenAI model to use for classification. 

Recommended (default):
- gpt-4o-mini: Fast, accurate, cost-effective (~$0.15 input / $0.60 output per 1M tokens), great for real-time email classification.

Alternatives:
- gpt-4o: More powerful (~$2.50 input / $10 output per 1M tokens), for complex reasoning.
- gpt-5-nano: Advanced reasoning (~$0.10 input / $0.30 output per 1M tokens), but slower with reasoning overhead.

Models support different APIs and parameters."""
    )
    
    # API version for compatibility with different models
    openai_api_version: str = Field(
        default="2024-11-06",
        description="OpenAI API version to use (e.g., for GPT-5 compatibility)"
    )
    openai_max_tokens: int = Field(default=4000, ge=100, le=4000)
    openai_temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    # Email Provider Settings
    email_provider: Literal["gmail", "outlook", "both"] = Field(
        default="gmail",
        description="Email provider(s) to use"
    )

    # Gmail OAuth Configuration
    # File-based OAuth method (for interactive auth)
    gmail_credentials_path: Optional[str] = Field(
        default=None,
        description="Path to Gmail OAuth credentials JSON file (defaults to ~/.mail-agent/credentials.json)"
    )
    gmail_token_path: Optional[str] = Field(
        default=None,
        description="Path to Gmail OAuth token JSON file (defaults to ~/.mail-agent/token.json)"
    )
    # OAuth client credentials method (for headless/server automation)
    gmail_client_id: Optional[str] = Field(
        default=None,
        description="Gmail OAuth client ID"
    )
    gmail_client_secret: Optional[str] = Field(
        default=None,
        description="Gmail OAuth client secret"
    )
    gmail_refresh_token: Optional[str] = Field(
        default=None,
        description="Gmail OAuth refresh token"
    )

    # Outlook MCP Configuration
    outlook_mcp_command: str = Field(
        default="npx",
        description="Command to run Outlook MCP server"
    )
    outlook_mcp_args: str = Field(
        default="-y,@softeria/ms-365-mcp-server",
        description="Comma-separated arguments for Outlook MCP server"
    )
    outlook_client_id: Optional[str] = Field(default=None, description="Azure client ID")
    outlook_client_secret: Optional[str] = Field(default=None, description="Azure client secret")
    outlook_tenant_id: Optional[str] = Field(default=None, description="Azure tenant ID")
    outlook_user_id: Optional[str] = Field(
        default=None,
        description="Outlook user ID or userPrincipalName (required for app-only auth)"
    )

    # Classification Settings
    categories_file: Optional[str] = Field(
        default=None,
        description="Path to categories configuration file (defaults to ~/.mail-agent/categories.yaml)"
    )
    batch_size: int = Field(default=10, ge=1, le=100, description="Number of emails to process per batch")
    max_emails_per_run: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum emails to process in a single run"
    )
    classification_concurrency: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of concurrent classification tasks"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Optional[str] = Field(default="email_classifier.log", description="Log file path")

    # TUI Settings
    tui_refresh_rate: int = Field(default=4, ge=1, le=60, description="TUI refresh rate per second")
    enable_rich_tracebacks: bool = Field(default=True, description="Enable rich tracebacks")

    @classmethod
    def _get_default_env_file(cls) -> Optional[str]:
        """Get default .env file path from ~/.mail-agent."""
        env_file = get_config_dir() / ".env"
        return str(env_file) if env_file.exists() else None

    model_config = SettingsConfigDict(
        env_file=None,  # Will be set via _env_file parameter
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    def __init__(self, **kwargs):
        """Initialize settings with default paths in ~/.mail-agent."""
        config_dir = get_config_dir()
        
        # Set default paths if not provided
        if "categories_file" not in kwargs or not kwargs.get("categories_file"):
            kwargs["categories_file"] = str(config_dir / "categories.yaml")
        
        if "gmail_credentials_path" not in kwargs or not kwargs.get("gmail_credentials_path"):
            kwargs["gmail_credentials_path"] = str(config_dir / "credentials.json")
        
        if "gmail_token_path" not in kwargs or not kwargs.get("gmail_token_path"):
            kwargs["gmail_token_path"] = str(config_dir / "token.json")
        
        # Set env_file to ~/.mail-agent/.env if not specified
        if "_env_file" not in kwargs:
            env_file = config_dir / ".env"
            if env_file.exists():
                kwargs["_env_file"] = str(env_file)
        
        super().__init__(**kwargs)

    @field_validator("outlook_mcp_args")
    @classmethod
    def parse_comma_separated(cls, v: str) -> List[str]:
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [arg.strip() for arg in v.split(",")]
        return v

    def get_outlook_mcp_args(self) -> List[str]:
        """Get Outlook MCP args as list."""
        if isinstance(self.outlook_mcp_args, str):
            return [arg.strip() for arg in self.outlook_mcp_args.split(",")]
        return self.outlook_mcp_args

    def validate_provider_config(self) -> None:
        """Validate that required configuration is present for selected provider."""
        if self.email_provider in ("gmail", "both"):
            # check if using file-based auth OR client credentials method
            has_file_auth = self.gmail_credentials_path is not None
            has_client_auth = all([
                self.gmail_client_id,
                self.gmail_client_secret,
                self.gmail_refresh_token
            ])
            
            if not (has_file_auth or has_client_auth):
                raise ValueError(
                    "Gmail provider requires either:\n"
                    "  - GMAIL_CREDENTIALS_PATH (file-based OAuth), OR\n"
                    "  - GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET + GMAIL_REFRESH_TOKEN (client credentials)"
                )

        if self.email_provider in ("outlook", "both"):
            required_outlook = {
                "OUTLOOK_CLIENT_ID": self.outlook_client_id,
                "OUTLOOK_CLIENT_SECRET": self.outlook_client_secret,
                "OUTLOOK_TENANT_ID": self.outlook_tenant_id
            }
            missing = [k for k, v in required_outlook.items() if not v]
            if missing:
                raise ValueError(f"Missing Outlook configuration: {', '.join(missing)}")


class ConfigurationManager:
    """Manages application configuration including settings and categories."""

    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration manager.

        Args:
            env_file: Optional path to .env file (defaults to ~/.mail-agent/.env)
        """
        if env_file and os.path.exists(env_file):
            self.settings = Settings(_env_file=env_file)
        else:
            # Try ~/.mail-agent/.env first, then fall back to no env file
            default_env = get_config_dir() / ".env"
            if default_env.exists():
                self.settings = Settings(_env_file=str(default_env))
            else:
                self.settings = Settings()

        self.classification_config: Optional[ClassificationConfig] = None
        
        # Create default categories.yaml if it doesn't exist
        self._ensure_default_categories()

    def _ensure_default_categories(self) -> None:
        """Create default categories.yaml if it doesn't exist."""
        categories_path = Path(self.settings.categories_file)
        if not categories_path.exists():
            # Copy from package if available, or create default
            try:
                # Try to find default categories in package
                package_categories = Path(__file__).parent / "categories.yaml"
                if package_categories.exists():
                    import shutil
                    shutil.copy(package_categories, categories_path)
                else:
                    # Create minimal default
                    default_categories = {
                        "categories": [
                            {
                                "name": "Security & 2FA",
                                "description": "Multi-factor authentication codes, password resets, and critical security alerts.",
                                "keywords": ["verification code", "authentication", "2FA", "OTP", "password reset"],
                                "priority_boost": 3
                            },
                            {
                                "name": "Work & Projects",
                                "description": "Professional correspondence, meeting invitations, project updates.",
                                "keywords": ["meeting", "project", "deadline"],
                                "priority_boost": 2
                            }
                        ],
                        "default_priority": 2,
                        "auto_apply_labels": True,
                        "create_missing_labels": True
                    }
                    with open(categories_path, "w", encoding="utf-8") as f:
                        yaml.dump(default_categories, f, default_flow_style=False)
            except Exception as e:
                # If we can't create it, that's ok - will error later when loading
                pass

    def load_categories(self) -> ClassificationConfig:
        """
        Load category definitions from YAML file.

        Returns:
            ClassificationConfig with loaded categories

        Raises:
            FileNotFoundError: If categories file doesn't exist
            ValueError: If categories file is invalid
        """
        # Ensure categories_file is set
        if not self.settings.categories_file:
            self.settings.categories_file = str(get_config_dir() / "categories.yaml")
        
        categories_path = Path(self.settings.categories_file)

        if not categories_path.exists():
            raise FileNotFoundError(f"Categories file not found: {categories_path}")

        try:
            with open(categories_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "categories" not in data:
                raise ValueError("Invalid categories file: missing 'categories' key")

            categories = [CategoryDefinition(**cat) for cat in data["categories"]]

            self.classification_config = ClassificationConfig(
                categories=categories,
                default_priority=data.get("default_priority", 2),
                auto_apply_labels=data.get("auto_apply_labels", True),
                create_missing_labels=data.get("create_missing_labels", True)
            )

            return self.classification_config

        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse categories YAML: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load categories: {e}")

    def get_category_names(self) -> List[str]:
        """Get list of all category names."""
        if not self.classification_config:
            self.load_categories()
        return [cat.name for cat in self.classification_config.categories]

    def get_category_descriptions(self) -> dict[str, str]:
        """Get mapping of category names to descriptions."""
        if not self.classification_config:
            self.load_categories()
        return {cat.name: cat.description for cat in self.classification_config.categories}

    def validate(self) -> None:
        """Validate entire configuration."""
        # Validate settings
        self.settings.validate_provider_config()

        # Validate categories
        if not self.classification_config:
            self.load_categories()

        if not self.classification_config.categories:
            raise ValueError("No categories defined in configuration")

        # Validate OpenAI API key format
        if not self.settings.openai_api_key.startswith("sk-"):
            raise ValueError("Invalid OpenAI API key format")


# Global configuration instance
_config: Optional[ConfigurationManager] = None


def get_config(env_file: Optional[str] = None) -> ConfigurationManager:
    """
    Get or create global configuration instance.

    Args:
        env_file: Optional path to .env file

    Returns:
        ConfigurationManager instance
    """
    global _config
    if _config is None:
        _config = ConfigurationManager(env_file)
        _config.load_categories()
    return _config


def reload_config(env_file: Optional[str] = None) -> ConfigurationManager:
    """
    Force reload of configuration.

    Args:
        env_file: Optional path to .env file

    Returns:
        New ConfigurationManager instance
    """
    global _config
    _config = ConfigurationManager(env_file)
    _config.load_categories()
    return _config
