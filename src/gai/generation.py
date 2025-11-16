"""Generation logic for interacting with Google GenAI API."""

import logging
import os
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types

from .exceptions import GenerationError
from .templates import render_system_instruction, render_user_instruction

logger = logging.getLogger(__name__)


def prepare_prompt_contents(config: dict[str, Any], template_variables: dict[str, str]) -> list[types.Content]:
    """
    Generates the list of Content objects for the API call by applying
    template variables to the defined prompt templates (excluding system instruction).
    """
    user_instruction_text = render_user_instruction(config, template_variables)
    if user_instruction_text is None:
        user_instruction_text = ""
    logger.debug(f"Templated user instruction part:\n{user_instruction_text}")

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=user_instruction_text)]),
    ]
    return contents


def prepare_generate_content_config_dict(config: dict[str, Any], template_variables: dict[str, str]) -> dict[str, Any]:
    """
    Generates the configuration dictionary for the generate_content API call.
    Applies template variables to the system instruction using Jinja2.
    Only includes non-None values to avoid potential API compatibility issues.
    """
    temperature = config.get("temperature")
    response_mime_type = config.get("response-mime-type")
    max_output_tokens = config.get("max-output-tokens")

    logger.info(f"Using temperature: {temperature}")
    logger.info(f"Using response_mime_type: {response_mime_type}")
    if max_output_tokens is not None:
        logger.info(f"Using max_output_tokens: {max_output_tokens}")

    system_instruction_text = render_system_instruction(config, template_variables)
    logger.debug(f"Templated System Instruction:\n{system_instruction_text or 'None'}")

    # Build config dict with only non-None values for better API compatibility
    generate_config_dict: dict[str, Any] = {
        "temperature": temperature,
        "response_mime_type": response_mime_type,
    }

    if max_output_tokens is not None:
        generate_config_dict["max_output_tokens"] = max_output_tokens

    if system_instruction_text is not None:
        generate_config_dict["system_instruction"] = system_instruction_text

    return generate_config_dict


def execute_generation_stream(
    client: genai.Client, model_name: str, contents: list[types.Content], config_dict: dict[str, Any]
) -> Generator[types.GenerateContentResponse, None, None]:
    """Executes the streaming generation API call."""
    logger.info(f"Executing streaming generation API call for model '{model_name}'...")
    logger.debug(f"API Call Config: {config_dict}")

    return client.models.generate_content_stream(
        model=model_name, contents=contents, config=types.GenerateContentConfig(**config_dict)
    )


def stream_output(stream_generator: Generator[types.GenerateContentResponse, None, None]) -> None:
    """Consumes the generator from the API call and streams the text output to stdout.

    Raises:
        GenerationError: If the prompt is blocked or generation fails.
    """
    logger.info("Streaming content to stdout...")
    try:
        for chunk in stream_generator:
            if chunk.text:
                print(chunk.text, end="")
        print()
        sys.stdout.flush()
        logger.info("Generation streaming finished.")
    except types.generation_types.BlockedPromptException as e:
        block_reason = (
            e.prompt_feedback.block_reason.name if e.prompt_feedback and e.prompt_feedback.block_reason else "Unknown"
        )
        raise GenerationError(f"Prompt was blocked. Reason: {block_reason}") from e
    except types.generation_types.StopCandidateException as e:
        finish_reason = (
            e.candidate.finish_reason.name if hasattr(e, "candidate") and e.candidate.finish_reason else "Unknown"
        )
        logger.warning(f"Generation may be incomplete. Reason: {finish_reason}")
        # Don't raise for StopCandidateException - it's a warning, not a fatal error
    except Exception as e:
        raise GenerationError(f"Error during streaming output: {e}") from e


def collect_output(stream_generator: Generator[types.GenerateContentResponse, None, None]) -> str:
    """Collect the entire streamed output into a single string."""

    parts: list[str] = []
    for chunk in stream_generator:
        if chunk.text:
            parts.append(chunk.text)
    return "".join(parts)


def extract_between_tags(text: str, tag_name: str) -> str:
    """Extract the substring between <TAG> and </TAG> from text."""

    start_tag = f"<{tag_name}>"
    end_tag = f"</{tag_name}>"

    start_index = text.find(start_tag)
    if start_index == -1:
        raise GenerationError(f"Tag '{start_tag}' not found in generation output.")

    start_index += len(start_tag)
    end_index = text.find(end_tag, start_index)
    if end_index == -1:
        raise GenerationError(f"Closing tag '{end_tag}' not found in generation output.")

    return text[start_index:end_index]


def _emit_captured_output(captured_text: str, output_file: Optional[str]) -> None:
    if output_file:
        Path(output_file).write_text(captured_text, encoding="utf-8")
        logger.info("Captured output written to %s", output_file)
    else:
        end = "" if captured_text.endswith("\n") else "\n"
        print(captured_text, end=end)


def generate(
    config: dict[str, Any],
    template_variables: dict[str, str],
    *,
    capture_tag: Optional[str] = None,
    output_file: Optional[str] = None,
) -> None:
    """
    Orchestrates the generation process: prepares prompt, prepares config,
    executes API call, and streams output.

    Raises:
        GenerationError: If generation fails for any reason.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            logger.warning("Using deprecated GEMINI_API_KEY environment variable. Please use GOOGLE_API_KEY instead.")
        else:
            raise GenerationError("GOOGLE_API_KEY environment variable not set.")

    client = genai.Client(api_key=api_key)
    logger.debug("GenAI client initialized.")

    contents = prepare_prompt_contents(config, template_variables)
    generate_config_dict = prepare_generate_content_config_dict(config, template_variables)
    model_name = config["model"]
    logger.info(f"Using model: {model_name}")
    logger.debug(f"GenerateContentConfig dictionary for API call: {generate_config_dict}")

    try:
        stream_generator = execute_generation_stream(client, model_name, contents, generate_config_dict)
        if capture_tag:
            full_text = collect_output(stream_generator)
            captured = extract_between_tags(full_text, capture_tag)
            _emit_captured_output(captured, output_file)
        else:
            stream_output(stream_generator)
    except GenerationError:
        raise
    except Exception as e:
        raise GenerationError(f"An error occurred during the generation process: {e}") from e
