from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape

from forgeapi.exceptions import ForgeAPIConfigError


class TemplateRenderer:
    """Jinja2 renderer for mail templates.

    HTML templates (``.html`` / ``.htm`` / ``.xml``) are auto-escaped, text
    templates are not.  A variable missing from the context raises instead of
    rendering an empty string — a half-empty e-mail must not go out unnoticed.
    """

    def __init__(self, directory: str) -> None:
        self._directory = directory
        self._env = Environment(
            loader=FileSystemLoader(directory),
            autoescape=select_autoescape(["html", "htm", "xml"], default=False),
            undefined=StrictUndefined,
        )

    def render(self, name: str, context: dict) -> str:
        try:
            return self._env.get_template(name).render(**context)
        except TemplateNotFound as exc:
            raise ForgeAPIConfigError(
                f"Mail template '{name}' not found in '{self._directory}'.",
                hint='Check the Mailable template name and "templates" in the \"mail\" section of config/app.py.',
            ) from exc
