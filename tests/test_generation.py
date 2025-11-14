"""Tests for generation module with Google GenAI API."""

import os

import pytest
from google import genai
from google.genai import types


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
    chunks = []
    for chunk in stream:
        if chunk.text:
            chunks.append(chunk.text)

    # Verify we got chunks
    assert len(chunks) > 0

    # Combine and verify content
    full_text = "".join(chunks)
    assert len(full_text) > 0
    response_lower = full_text.lower()
    assert any(greeting in response_lower for greeting in ["hi", "hello", "hey", "greetings"])
