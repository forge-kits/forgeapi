import pytest
from forgeapi.exceptions import ForgeAPIError, ForgeAPIConfigError, ForgeAPIImportError


class TestForgeAPIError:
    def test_message_only(self):
        err = ForgeAPIError("something went wrong")
        assert "something went wrong" in str(err)
        assert err.hint == ""

    def test_message_with_hint(self):
        err = ForgeAPIError("bad config", hint="check forgeapi.toml")
        assert "bad config" in str(err)
        assert "check forgeapi.toml" in str(err)
        assert err.hint == "check forgeapi.toml"

    def test_is_exception(self):
        with pytest.raises(ForgeAPIError):
            raise ForgeAPIError("oops")

    def test_config_error_inherits(self):
        err = ForgeAPIConfigError("bad value", hint="use a valid strategy")
        assert isinstance(err, ForgeAPIError)
        assert isinstance(err, ForgeAPIConfigError)

    def test_import_error_inherits_both(self):
        err = ForgeAPIImportError("missing dep", hint="pip install forge-kits[auth]")
        assert isinstance(err, ForgeAPIError)
        assert isinstance(err, ImportError)

    def test_empty_message_does_not_raise(self):
        err = ForgeAPIError("")
        assert isinstance(err, ForgeAPIError)

    def test_hint_default_is_empty_string(self):
        err = ForgeAPIError("msg")
        assert isinstance(err.hint, str)
        assert err.hint == ""

    def test_message_with_empty_hint_equals_message_without_hint(self):
        err1 = ForgeAPIError("msg")
        err2 = ForgeAPIError("msg", hint="")
        assert str(err1) == str(err2)

    def test_status_code_default(self):
        err = ForgeAPIError("msg")
        assert err.status_code == 500

    def test_status_code_override(self):
        err = ForgeAPIError("msg", status_code=503)
        assert err.status_code == 503

    def test_import_error_status_code(self):
        err = ForgeAPIImportError("missing")
        assert err.status_code == 501
