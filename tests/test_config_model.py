"""Tests for configuration data model."""

import pytest

from gai.config_model import Config
from gai.exceptions import ConfigError


def test_config_valid():
    """Test creating valid Config."""
    config = Config(
        model="gemini-flash-latest",
        temperature=0.5,
        response_mime_type="text/plain",
        max_output_tokens=1000,
        system_instruction="You are helpful",
        user_instruction="User: {{ input }}",
    )

    assert config.model == "gemini-flash-latest"
    assert config.temperature == 0.5
    assert config.max_output_tokens == 1000


def test_config_temperature_too_low():
    """Test temperature below 0.0 raises error."""
    with pytest.raises(ConfigError, match="temperature must be between"):
        Config(
            model="gemini-flash-latest",
            temperature=-0.1,
            response_mime_type="text/plain",
            max_output_tokens=None,
            system_instruction=None,
            user_instruction="Test",
        )


def test_config_temperature_too_high():
    """Test temperature above 2.0 raises error."""
    with pytest.raises(ConfigError, match="temperature must be between"):
        Config(
            model="gemini-flash-latest",
            temperature=2.1,
            response_mime_type="text/plain",
            max_output_tokens=None,
            system_instruction=None,
            user_instruction="Test",
        )


def test_config_temperature_boundary_values():
    """Test temperature boundary values are accepted."""
    # Test lower boundary
    config_min = Config(
        model="gemini-flash-latest",
        temperature=0.0,
        response_mime_type="text/plain",
        max_output_tokens=None,
        system_instruction=None,
        user_instruction="Test",
    )
    assert config_min.temperature == 0.0

    # Test upper boundary
    config_max = Config(
        model="gemini-flash-latest",
        temperature=2.0,
        response_mime_type="text/plain",
        max_output_tokens=None,
        system_instruction=None,
        user_instruction="Test",
    )
    assert config_max.temperature == 2.0


def test_config_max_tokens_negative():
    """Test negative max_output_tokens raises error."""
    with pytest.raises(ConfigError, match="max_output_tokens must be positive"):
        Config(
            model="gemini-flash-latest",
            temperature=0.5,
            response_mime_type="text/plain",
            max_output_tokens=-1,
            system_instruction=None,
            user_instruction="Test",
        )


def test_config_max_tokens_zero():
    """Test zero max_output_tokens raises error."""
    with pytest.raises(ConfigError, match="max_output_tokens must be positive"):
        Config(
            model="gemini-flash-latest",
            temperature=0.5,
            response_mime_type="text/plain",
            max_output_tokens=0,
            system_instruction=None,
            user_instruction="Test",
        )


def test_config_max_tokens_none():
    """Test None max_output_tokens is accepted."""
    config = Config(
        model="gemini-flash-latest",
        temperature=0.5,
        response_mime_type="text/plain",
        max_output_tokens=None,
        system_instruction=None,
        user_instruction="Test",
    )
    assert config.max_output_tokens is None


def test_config_empty_model():
    """Test empty model name raises error."""
    with pytest.raises(ConfigError, match="model name cannot be empty"):
        Config(
            model="",
            temperature=0.5,
            response_mime_type="text/plain",
            max_output_tokens=None,
            system_instruction=None,
            user_instruction="Test",
        )


def test_config_whitespace_model():
    """Test whitespace-only model name raises error."""
    with pytest.raises(ConfigError, match="model name cannot be empty"):
        Config(
            model="   ",
            temperature=0.5,
            response_mime_type="text/plain",
            max_output_tokens=None,
            system_instruction=None,
            user_instruction="Test",
        )


def test_config_invalid_mime_type():
    """Test invalid response_mime_type raises error."""
    with pytest.raises(ConfigError, match="response_mime_type must be one of"):
        Config(
            model="gemini-flash-latest",
            temperature=0.5,
            response_mime_type="text/html",
            max_output_tokens=None,
            system_instruction=None,
            user_instruction="Test",
        )


def test_config_to_dict():
    """Test converting Config to dictionary."""
    config = Config(
        model="gemini-flash-latest",
        temperature=0.5,
        response_mime_type="text/plain",
        max_output_tokens=1000,
        system_instruction="System",
        user_instruction="User",
    )

    result = config.to_dict()

    assert result["model"] == "gemini-flash-latest"
    assert result["temperature"] == 0.5
    assert result["response-mime-type"] == "text/plain"
    assert result["max-output-tokens"] == 1000
    assert result["system-instruction"] == "System"
    assert result["user-instruction"] == "User"


def test_config_from_dict():
    """Test creating Config from dictionary."""
    config_dict = {
        "model": "gemini-pro",
        "temperature": 0.8,
        "response-mime-type": "application/json",
        "max-output-tokens": 2000,
        "system-instruction": "System",
        "user-instruction": "User",
    }

    config = Config.from_dict(config_dict)

    assert config.model == "gemini-pro"
    assert config.temperature == 0.8
    assert config.response_mime_type == "application/json"
    assert config.max_output_tokens == 2000


def test_config_from_dict_with_defaults():
    """Test creating Config from dictionary with missing keys uses defaults."""
    config_dict = {}

    config = Config.from_dict(config_dict)

    assert config.model == "gemini-flash-latest"
    assert config.temperature == 0.1
    assert config.response_mime_type == "text/plain"
    assert config.max_output_tokens is None
