#!/usr/bin/env python3
"""Build script to create standalone gai.py from modular source."""

import pathlib

# Define module order for concatenation
MODULE_ORDER = [
    "src/gai/__init__.py",
    "src/gai/templates.py",
    "src/gai/config.py",
    "src/gai/generation.py",
    "src/gai/cli.py",
    "src/gai/__main__.py",
]

SHEBANG = """#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "google-genai>=1.15.0",
#     "tomli>=2.0.0; python_version < '3.11'",
#     "jinja2>=3.1.0",
# ]
# ///
"""


def extract_module_content(filepath: pathlib.Path) -> str:
    """Extract content from a module, removing docstrings and imports that will be consolidated."""
    content = filepath.read_text()
    lines = content.split("\n")

    # Skip module docstring at the beginning
    result_lines = []
    in_module_docstring = False
    docstring_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip initial module docstring
        if i < 5 and (stripped.startswith('"""') or stripped.startswith("'''")):
            if not in_module_docstring:
                in_module_docstring = True
                docstring_start = i
            elif in_module_docstring and len(stripped) > 3:
                in_module_docstring = False
                continue
        elif in_module_docstring:
            continue
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def build_standalone() -> str:
    """Build standalone script from modular sources."""
    output = [SHEBANG, ""]

    # Collect all imports
    imports = set()
    module_contents = []

    for module_path in MODULE_ORDER:
        filepath = pathlib.Path(module_path)
        if not filepath.exists():
            print(f"Warning: {module_path} not found, skipping")
            continue

        content = filepath.read_text()
        lines = content.split("\n")

        module_imports = []
        other_lines = []
        skip_docstring = True
        in_docstring = False

        for line in lines:
            stripped = line.strip()

            # Skip module-level docstring
            if skip_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
                if not in_docstring:
                    in_docstring = True
                    if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                        skip_docstring = False
                        in_docstring = False
                    continue
                in_docstring = False
                skip_docstring = False
                continue
            if in_docstring:
                continue

            # Collect imports
            if line.startswith("import ") or line.startswith("from "):
                # Skip relative imports
                if not line.startswith("from ."):
                    imports.add(line)
            elif (stripped and not stripped.startswith("#")) or stripped.startswith("#"):
                other_lines.append(line)
            else:
                other_lines.append(line)

        if other_lines:
            # Add section separator
            module_name = filepath.stem
            module_contents.append(f"\n# --- {module_name} ---\n")
            module_contents.append("\n".join(other_lines))

    # Add consolidated imports
    sorted_imports = sorted(imports)
    output.extend(sorted_imports)
    output.append("")

    # Add all module contents
    output.extend(module_contents)

    return "\n".join(output)


def main():
    """Main build function."""
    output_file = pathlib.Path("gai.py")

    print("Building standalone gai.py from modular sources...")
    standalone_content = build_standalone()

    output_file.write_text(standalone_content)
    output_file.chmod(0o755)

    print(f"✓ Created {output_file} ({len(standalone_content)} bytes)")
    print("✓ Made executable")


if __name__ == "__main__":
    main()
