"""markdown-gost CLI (T020).

Commands: ``convert``, ``validate``. Exit codes: ``0`` ok, ``1`` user error
(config/parse), ``2`` system error / usage error.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn, cast

import click
import yaml

from markdown_gost import __version__
from markdown_gost.cli.commands.import_cmd import import_command
from markdown_gost.config.errors import ConfigError
from markdown_gost.config.loader import load_config_from_path, load_config_from_string
from markdown_gost.config.presets import available_presets
from markdown_gost.config.schema import Config
from markdown_gost.convert import Format
from markdown_gost.convert import convert as convert_pipeline
from markdown_gost.core.parser import parse as parse_markdown
from markdown_gost.storage import get_storage

_DEFAULT_CONFIG = "preset: gost-7-32-2017\n"
_VALID_FORMATS: tuple[str, ...] = ("docx", "pdf")
_LOGGER = logging.getLogger("markdown_gost.cli")
_CONFIG_HELP = (
    "Path to YAML config (preset + overrides) or a built-in preset name "
    f"({', '.join(available_presets())}). "
    "Defaults to the built-in default preset."
)


def _resolve_format(explicit: str | None, output: Path | None) -> Format:
    if explicit is not None:
        return cast(Format, explicit.lower())
    if output is not None:
        suffix = output.suffix.lstrip(".").lower()
        if suffix in _VALID_FORMATS:
            return cast(Format, suffix)
    return "docx"


def _load_config(config_path: str | None) -> Config:
    """Resolve ``--config``: YAML file path, built-in preset name, or default."""
    if config_path is None:
        return load_config_from_string(_DEFAULT_CONFIG)
    path = Path(config_path)
    if path.is_file():
        return load_config_from_path(path)
    if config_path in available_presets():
        return load_config_from_string(f"preset: {config_path}\n")
    _unknown_config(config_path)


def _unknown_config(value: str) -> NoReturn:
    _user_error(
        f"--config {value!r} is neither an existing config file nor a built-in "
        f"preset (available presets: {', '.join(available_presets())})"
    )


def _user_error(message: str) -> NoReturn:
    raise click.ClickException(message)


def _system_error(message: str) -> NoReturn:
    click.echo(f"Error: {message}", err=True)
    sys.exit(2)


def _execute(action: Callable[[], Any]) -> Any:
    """Run *action* and translate exceptions to documented exit codes.

    ``ConfigError`` / ``ValueError`` (incl. pydantic ``ValidationError``) /
    ``yaml.YAMLError`` → exit 1. Anything else → exit 2.
    """

    try:
        return action()
    except click.ClickException:
        raise
    except (ConfigError, ValueError, yaml.YAMLError) as exc:
        _user_error(str(exc))
    except Exception as exc:
        _LOGGER.debug("system error", exc_info=True)
        _system_error(str(exc))


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="markdown-gost")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable DEBUG-level logging.",
)
def cli(verbose: bool) -> None:
    """markdown-gost — Markdown → DOCX/PDF по ГОСТ.

    Пресет ГОСТа задаётся в YAML-конфиге или именем встроенного пресета
    в ``--config`` (см. ADR-0004).
    """

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


@cli.command("convert")
@click.argument(
    "input_path",
    metavar="INPUT",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output file. Defaults to <input>.<format>.",
)
@click.option(
    "--config",
    "config_path",
    type=click.STRING,
    default=None,
    help=_CONFIG_HELP,
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(list(_VALID_FORMATS), case_sensitive=False),
    default=None,
    help="Output format. Inferred from --output extension if omitted.",
)
def convert_command(
    input_path: Path,
    output: Path | None,
    config_path: str | None,
    fmt: str | None,
) -> None:
    """Convert INPUT markdown into the chosen format."""

    resolved_fmt = _resolve_format(fmt, output)
    if output is None:
        output = input_path.with_suffix(f".{resolved_fmt}")

    def _do() -> None:
        config = _load_config(config_path)
        markdown = input_path.read_text(encoding="utf-8")
        storage = get_storage(default_base_dir=input_path.parent)
        _LOGGER.debug(
            "convert input=%s output=%s format=%s preset=%s",
            input_path,
            output,
            resolved_fmt,
            config.preset,
        )
        data = convert_pipeline(
            markdown, config, format=resolved_fmt, storage=storage
        )
        assert output is not None
        output.write_bytes(data)
        click.echo(f"Wrote {output}")

    _execute(_do)


@cli.command("validate")
@click.argument(
    "input_path",
    metavar="INPUT",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--config",
    "config_path",
    type=click.STRING,
    default=None,
    help=_CONFIG_HELP,
)
def validate_command(input_path: Path, config_path: str | None) -> None:
    """Validate INPUT markdown + config without producing output."""

    def _do() -> None:
        config = _load_config(config_path)
        markdown = input_path.read_text(encoding="utf-8")
        from markdown_gost.render.bibliography import BibliographyIndex
        from markdown_gost.render.references import prepare_document

        document = prepare_document(parse_markdown(markdown), config)
        BibliographyIndex.from_document(document, config)
        click.echo(f"OK (preset={config.preset})")

    _execute(_do)


cli.add_command(import_command)


if __name__ == "__main__":
    cli()
