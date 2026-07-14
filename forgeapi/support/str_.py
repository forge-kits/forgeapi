from __future__ import annotations

import re
import secrets
import string


class Str:
    @staticmethod
    def limit(value: str, length: int, end: str = "...") -> str:
        """'Hello world', 5 → 'Hello...'"""
        if len(value) <= length:
            return value
        return value[:length] + end

    @staticmethod
    def slug(value: str, separator: str = "-") -> str:
        """'Hello World!' → 'hello-world'"""
        value = value.lower().strip()
        value = re.sub(r"[^\w\s-]", "", value)
        value = re.sub(r"[\s_]+", separator, value)
        value = re.sub(rf"{re.escape(separator)}+", separator, value)
        return value.strip(separator)

    @staticmethod
    def random(length: int = 16, alphabet: str | None = None) -> str:
        """Generate a cryptographically random string of given length."""
        chars = alphabet or (string.ascii_letters + string.digits)
        return "".join(secrets.choice(chars) for _ in range(length))

    @staticmethod
    def title(value: str) -> str:
        """'hello world' → 'Hello World'"""
        return value.title()

    @staticmethod
    def snake(value: str) -> str:
        """'HelloWorld' or 'hello-world' → 'hello_world'"""
        value = re.sub(r"[-\s]+", "_", value)
        value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
        value = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", value)
        return value.lower()

    @staticmethod
    def camel(value: str) -> str:
        """'hello_world' → 'helloWorld'"""
        parts = re.split(r"[-_\s]+", value)
        return parts[0].lower() + "".join(p.title() for p in parts[1:])

    @staticmethod
    def pascal(value: str) -> str:
        """'hello_world' → 'HelloWorld'"""
        return "".join(p.title() for p in re.split(r"[-_\s]+", value))

    @staticmethod
    def truncate_words(value: str, count: int, end: str = "...") -> str:
        """Truncate to N words: 'hello world foo', 2 → 'hello world...'"""
        words = value.split()
        if len(words) <= count:
            return value
        return " ".join(words[:count]) + end

    @staticmethod
    def contains(value: str, search: str, case_sensitive: bool = True) -> bool:
        if case_sensitive:
            return search in value
        return search.lower() in value.lower()

    @staticmethod
    def starts_with(value: str, prefix: str) -> bool:
        return value.startswith(prefix)

    @staticmethod
    def ends_with(value: str, suffix: str) -> bool:
        return value.endswith(suffix)

    @staticmethod
    def strip_tags(value: str) -> str:
        """Remove HTML tags: '<b>Hello</b>' → 'Hello'"""
        return re.sub(r"<[^>]+>", "", value)

    @staticmethod
    def mask(value: str, char: str = "*", start: int = 0, length: int | None = None) -> str:
        """'1234567890', char='*', start=4 → '1234******'"""
        end = start + length if length is not None else len(value)
        return value[:start] + char * (end - start) + value[end:]
