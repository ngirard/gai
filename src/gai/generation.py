"""Generation logic for interacting with Google GenAI API."""

import logging
import os
import sys
from collections.abc import Generator
from typing import Any

from google import genai
from google.genai import types

from .templates import render_template_string

logger = logging.getLogger(__name__)


def prepare_prompt_contents(config: dict[str, Any], template_variables: dict[str, str]) -> list[types.Content]:
    """
    Generates the list of Content objects for the API call by applying
    template variables to the defined prompt templates (excluding system instruction).
    """
    user_instruction_template_str = config.get("user-instruction")

    user_instruction_text = render_template_string(
        user_instruction_template_str, template_variables, "user-instruction"
    )
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
    """
    temperature = config.get("temperature")
    response_mime_type = config.get("response-mime-type")
    max_output_tokens = config.get("max-output-tokens")
    system_instruction_template_str = config.get("system-instruction")

    logger.info(f"Using temperature: {temperature}")
    logger.info(f"Using response_mime_type: {response_mime_type}")
    if max_output_tokens is not None:
        logger.info(f"Using max_output_tokens: {max_output_tokens}")

    system_instruction_text = render_template_string(
        system_instruction_template_str, template_variables, "system-instruction"
    )
    logger.debug(f"Templated System Instruction:\n{system_instruction_text or 'None'}")

    generate_config_dict: dict[str, Any] = {
        "temperature": temperature,
        "response_mime_type": response_mime_type,
        "max_output_tokens": max_output_tokens,
        "system_instruction": system_instruction_text,
    }
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
    """Consumes the generator from the API call and streams the text output to stdout."""
    logger.info("Streaming content to stdout...")
    try:
        for chunk in stream_generator:
            if chunk.text:
                print(chunk.text, end="")
        print()
        sys.stdout.flush()
        logger.info("Generation streaming finished.")
    except types.generation_types.BlockedPromptException as e:
        logger.error(f"Prompt was blocked: {e}")
        block_reason = (
            e.prompt_feedback.block_reason.name if e.prompt_feedback and e.prompt_feedback.block_reason else "Unknown"
        )
        print(f"\nERROR: Prompt was blocked. Reason: {block_reason}", file=sys.stderr)
        sys.exit(1)
    except types.generation_types.StopCandidateException as e:
        logger.error(f"Generation stopped prematurely for a candidate: {e}")
        finish_reason = (
            e.candidate.finish_reason.name if hasattr(e, "candidate") and e.candidate.finish_reason else "Unknown"
        )
        print(f"\nWARNING: Generation may be incomplete. Reason: {finish_reason}", file=sys.stderr)
    except Exception as e:
        logger.error(f"Error during streaming output: {e}")
        raise


def generate(config: dict[str, Any], template_variables: dict[str, str]) -> None:
    """
    Orchestrates the generation process: prepares prompt, prepares config,
    executes API call, and streams output.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            logger.warning("Using deprecated GEMINI_API_KEY environment variable. Please use GOOGLE_API_KEY instead.")
        else:
            logger.error("Error: GOOGLE_API_KEY environment variable not set.")
            sys.exit(1)

    client = genai.Client(api_key=api_key)
    logger.debug("GenAI client initialized.")

    contents = prepare_prompt_contents(config, template_variables)
    generate_config_dict = prepare_generate_content_config_dict(config, template_variables)
    model_name = config.get("model", "gemini-2.0-flash-exp")
    logger.info(f"Using model: {model_name}")
    logger.debug(f"GenerateContentConfig dictionary for API call: {generate_config_dict}")

    try:
        stream_generator = execute_generation_stream(client, model_name, contents, generate_config_dict)
        stream_output(stream_generator)
    except Exception as e:
        logger.error(f"An error occurred during the generation process: {e}")
        sys.exit(1)
