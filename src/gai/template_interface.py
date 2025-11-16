"""Template interface introspection utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

import jinja2
from jinja2 import meta

from .exceptions import TemplateError
from .template_catalog import TemplateRecord, resolve_template_name
from .templates import create_jinja_env_from_catalog

OUTPUT_TAG_PATTERN = re.compile(r"<(O_[A-Za-z0-9_]+)>")


@dataclass(slots=True)
class TemplateInterface:
    """Describes the inferred interface of a template."""

    logical_name: str
    inputs: Mapping[str, str] = field(default_factory=dict)
    controls: Mapping[str, str] = field(default_factory=dict)
    mechanisms: Mapping[str, str] = field(default_factory=dict)
    outputs: set[str] = field(default_factory=set)
    other_variables: set[str] = field(default_factory=set)

    def cli_flags_for(self, prefixed_variables: Mapping[str, str]) -> list[str]:
        """Return sorted CLI flag representations for the provided mapping."""

        flags: list[str] = []
        for base_name in prefixed_variables.values():
            if base_name:
                flags.append(f"--{base_name}")
        return sorted(set(flags))


def build_template_interface(
    config: Mapping[str, Any],
    logical_name: str,
    *,
    catalog: Optional[Sequence[TemplateRecord]] = None,
    jinja_env: Optional[jinja2.Environment] = None,
) -> TemplateInterface:
    """Build the TemplateInterface for a logical template name."""

    records = list(catalog) if catalog is not None else None
    if records is None:
        from .template_catalog import build_template_catalog

        catalog_obj = build_template_catalog(config)
        records = list(catalog_obj.records)

    if jinja_env is None:
        jinja_env = create_jinja_env_from_catalog(records)

    record = resolve_template_name(records, logical_name)

    try:
        source = record.absolute_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem errors are rare
        raise TemplateError(f"Unable to read template '{logical_name}': {exc}") from exc

    try:
        ast = jinja_env.parse(source)
    except jinja2.exceptions.TemplateSyntaxError as exc:
        raise TemplateError(f"Unable to parse template '{logical_name}': {exc}") from exc

    undeclared = meta.find_undeclared_variables(ast)

    def _classify(prefix: str) -> dict[str, str]:
        names = sorted(v for v in undeclared if v.startswith(prefix))
        return {name: name[len(prefix) :].lstrip("_") for name in names}

    inputs = _classify("I_")
    controls = _classify("C_")
    mechanisms = _classify("M_")
    categorized = set(inputs) | set(controls) | set(mechanisms)
    other_variables = {var for var in undeclared if var not in categorized}

    outputs = set(OUTPUT_TAG_PATTERN.findall(source))

    return TemplateInterface(
        logical_name=logical_name,
        inputs=inputs,
        controls=controls,
        mechanisms=mechanisms,
        outputs=outputs,
        other_variables=other_variables,
    )
