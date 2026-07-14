from .logger import Logger

# forge-kits internal logger — all library logs go under "forgeapi.*"
log = Logger("forgeapi")

# User-facing logger — project code logs go under "app.*"
Log = Logger("app")

__all__ = ["Logger", "log", "Log"]
