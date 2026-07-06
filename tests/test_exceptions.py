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
