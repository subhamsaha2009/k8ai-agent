"""
k8ai configuration — load/save config from ~/.k8ai/
API keys stored in OS keychain (Windows Credential Manager / macOS Keychain).
"""

import os
import yaml
import keyring

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".k8ai")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
CUSTOM_TOOLS_DIR = os.path.join(CONFIG_DIR, "my_tools")
KEYRING_SERVICE = "k8ai"
KEYRING_KEY = "ai_api_key"


def ensure_config_dir():
    """Create ~/.k8ai/ and ~/.k8ai/my_tools/ if they don't exist."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(CUSTOM_TOOLS_DIR, exist_ok=True)


def save_config(provider: str, model: str, endpoint: str = None,
                api_version: str = None, api_key: str = None):
    """Save config to ~/.k8ai/config.yaml and API key to OS keychain."""
    ensure_config_dir()

    config = {"provider": provider, "model": model}
    if endpoint:
        config["endpoint"] = endpoint
    if api_version:
        config["api_version"] = api_version

    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    if api_key:
        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, api_key)


def load_config() -> dict | None:
    """Load config from ~/.k8ai/config.yaml + API key from keychain.
    Returns dict with all config values, or None if not configured."""
    if not os.path.exists(CONFIG_FILE):
        return None

    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f) or {}

    # Load API key from keychain
    api_key = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
    if api_key:
        config["api_key"] = api_key

    return config


def apply_config_to_env(config: dict):
    """Set environment variables from config so providers work unchanged."""
    os.environ["AI_PROVIDER"] = config.get("provider", "")
    if config.get("api_key"):
        os.environ["AI_API_KEY"] = config["api_key"]
    if config.get("model"):
        os.environ["AI_MODEL"] = config["model"]
    if config.get("endpoint"):
        os.environ["AI_ENDPOINT"] = config["endpoint"]
    if config.get("api_version"):
        os.environ["AI_API_VERSION"] = config["api_version"]


def show_config():
    """Print current config (without API key)."""
    config = load_config()
    if not config:
        return "No configuration found. Run 'k8ai init' to set up."

    lines = []
    lines.append(f"Provider:    {config.get('provider', 'not set')}")
    lines.append(f"Model:       {config.get('model', 'not set')}")
    if config.get("endpoint"):
        lines.append(f"Endpoint:    {config.get('endpoint')}")
    if config.get("api_version"):
        lines.append(f"API Version: {config.get('api_version')}")
    lines.append(f"API Key:     {'********' if config.get('api_key') else 'not set'}")
    lines.append(f"Config file: {CONFIG_FILE}")
    return "\n".join(lines)


def is_configured() -> bool:
    """Check if k8ai has been initialized."""
    return os.path.exists(CONFIG_FILE)
