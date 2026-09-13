class ConfigError(Exception):
    """Base class for configuration loading errors."""


class UnknownPresetError(ConfigError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown preset: {name!r}")
        self.name = name
