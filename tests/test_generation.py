"""Tests for generation module with Google GenAI API."""

import os
from unittest.mock import MagicMock, Mock

import pytest
from google import genai
from google.genai import types

from gai.generation import (
    execute_generation_stream,
    prepare_generate_content_config_dict,
    prepare_prompt_contents,
)


def test_prepare_prompt_contents_simple():
    """Test preparing prompt contents with simple template."""
    config = {
        "user-instruction": "Query: {{ input }}",
        "system-instruction": None,
    }
    variables = {"input": "What is AI?"}

    contents = prepare_prompt_contents(config, variables)

    assert len(contents) == 1
    assert contents[0].role == "user"
    assert "Query: What is AI?" in contents[0].parts[0].text


def test_prepare_prompt_contents_none_template():
    """Test preparing prompt contents with None template."""
    config = {
        "user-instruction": None,
        "system-instruction": None,
    }
    variables = {}

    contents = prepare_prompt_contents(config, variables)

    assert len(contents) == 1
    assert contents[0].parts[0].text == ""


def test_prepare_generate_content_config_dict():
    """Test preparing generation config dict."""
    config = {
        "temperature": 0.7,
        "response-mime-type": "text/plain",
        "max-output-tokens": 1000,
        "system-instruction": "You are a helpful assistant.",
    }
    variables = {}

    result = prepare_generate_content_config_dict(config, variables)

    assert result["temperature"] == 0.7
    assert result["response_mime_type"] == "text/plain"
    assert result["max_output_tokens"] == 1000
    assert result["system_instruction"] == "You are a helpful assistant."


def test_prepare_generate_content_config_dict_templated():
    """Test preparing generation config with templated system instruction."""
    config = {
        "temperature": 0.5,
        "response-mime-type": "application/json",
        "max-output-tokens": None,
        "system-instruction": "Expert in {{ topic }}",
    }
    variables = {"topic": "Python programming"}

    result = prepare_generate_content_config_dict(config, variables)

    assert result["temperature"] == 0.5
    assert result["system_instruction"] == "Expert in Python programming"
    assert result["max_output_tokens"] is None


def test_execute_generation_stream():
    """Test execute_generation_stream calls the API correctly."""
    mock_client = Mock(spec=genai.Client)
    mock_models = Mock()
    mock_client.models = mock_models

    mock_response = MagicMock()
    mock_models.generate_content_stream.return_value = mock_response

    model_name = "gemini-flash-latest"
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="Hello")])]
    config_dict = {"temperature": 0.5}

    result = execute_generation_stream(mock_client, model_name, contents, config_dict)

    assert result == mock_response
    mock_models.generate_content_stream.assert_called_once()
    call_kwargs = mock_models.generate_content_stream.call_args[1]
    assert call_kwargs["model"] == model_name
    assert call_kwargs["contents"] == contents


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None and os.environ.get("GEMINI_API_KEY") is None,
    reason="GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set",
)
def test_google_genai_simple_greeting():
    """
    Test that google-genai works fine with a simple 'say hi' prompt.
    Uses gemini-flash-lite-latest model as it's the cheapest option.
    """
    # Get API key (prefer GOOGLE_API_KEY, fallback to GEMINI_API_KEY)
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    assert api_key is not None, "API key should be available"

    # Initialize client
    client = genai.Client(api_key=api_key)

    # Prepare simple prompt
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="Say hi")])]

    # Use the cheapest model
    model_name = "gemini-flash-lite-latest"

    # Execute generation (non-streaming for easier testing)
    response = client.models.generate_content(model=model_name, contents=contents)

    # Verify we got a response
    assert response is not None
    assert response.text is not None
    assert len(response.text) > 0

    # Basic sanity check - response should contain a greeting
    response_lower = response.text.lower()
    assert any(greeting in response_lower for greeting in ["hi", "hello", "hey", "greetings"])


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None and os.environ.get("GEMINI_API_KEY") is None,
    reason="GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set",
)
def test_google_genai_streaming():
    """
    Test that google-genai streaming works fine.
    Uses gemini-flash-lite-latest model.
    """
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    assert api_key is not None

    client = genai.Client(api_key=api_key)
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="Say hello")])]
    model_name = "gemini-flash-lite-latest"

    # Execute streaming generation
    stream = client.models.generate_content_stream(model=model_name, contents=contents)

    # Collect chunks
    chunks = [chunk.text for chunk in stream if chunk.text]

    # Verify we got chunks
    assert len(chunks) > 0

    # Combine and verify content
    full_text = "".join(chunks)
    assert len(full_text) > 0
    response_lower = full_text.lower()
    assert any(greeting in response_lower for greeting in ["hi", "hello", "hey", "greetings"])
