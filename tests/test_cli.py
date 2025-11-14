"""Tests for CLI module."""

import pathlib
import tempfile

import pytest

from gai.cli import parse_template_args, process_template_values
from gai.exceptions import CliUsageError


def test_parse_template_args_simple():
    """Test parsing simple template arguments."""
    args = ["--document", "Test doc", "--input", "Test query"]
    result = parse_template_args(args)

    assert result["document"] == "Test doc"
    assert result["input"] == "Test query"


def test_parse_template_args_with_config():
    """Test parsing template args with config args mixed in."""
    args = [
        "--conf-temperature",
        "0.8",
        "--document",
        "Test doc",
        "--conf-model",
        "gemini-pro",
        "--input",
        "Query",
    ]
    result = parse_template_args(args)

    # Config args should be ignored, only template args returned
    assert result == {"document": "Test doc", "input": "Query"}
    assert "temperature" not in result
    assert "model" not in result


def test_parse_template_args_with_flags():
    """Test parsing template args with flags mixed in."""
    args = ["--debug", "--document", "Doc", "--show-prompt", "--input", "Query"]
    result = parse_template_args(args)

    # Flags should be ignored
    assert result == {"document": "Doc", "input": "Query"}


def test_parse_template_args_file_reference():
    """Test parsing template args with @: file reference."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Content from file")
        temp_path = f.name

    try:
        args = ["--document", f"@:{temp_path}"]
        result = parse_template_args(args)

        assert result["document"] == "Content from file"
    finally:
        pathlib.Path(temp_path).unlink()


def test_parse_template_args_missing_value():
    """Test parsing fails when template arg is missing value."""
    args = ["--document"]

    with pytest.raises(CliUsageError, match="requires a value"):
        parse_template_args(args)


def test_parse_template_args_unexpected_arg():
    """Test parsing fails with non -- argument."""
    args = ["document"]

    with pytest.raises(CliUsageError, match="Unexpected argument"):
        parse_template_args(args)


def test_parse_template_args_empty():
    """Test parsing empty args returns empty dict."""
    result = parse_template_args([])
    assert result == {}


def test_process_template_values_direct():
    """Test process_template_values with direct values."""
    pairs = [("--document", "Direct value"), ("--input", "Another value")]
    result = list(process_template_values(iter(pairs)))

    assert result == [("document", "Direct value"), ("input", "Another value")]


def test_process_template_values_file():
    """Test process_template_values with @: file reference."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("File content")
        temp_path = f.name

    try:
        pairs = [("--document", f"@:{temp_path}")]
        result = list(process_template_values(iter(pairs)))

        assert result == [("document", "File content")]
    finally:
        pathlib.Path(temp_path).unlink()
