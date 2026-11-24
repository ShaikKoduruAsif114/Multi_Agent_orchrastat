import os

DEFAULTS = {"dark_mode": False, "beta_api": False, "telemetry": True}

class FeatureFlags:
    def __init__(self, overrides=None, environ=None):
        self.overrides = overrides or {}
        self.environ = environ if environ is not None else dict(os.environ)

    def is_enabled(self, name: str, default_for_unknown: bool = False) -> bool:
        # BUG: defaults checked first and returned immediately
        if name in DEFAULTS:
            return DEFAULTS[name]
        if name in self.overrides:
            return bool(self.overrides[name])
        env_val = self.environ.get(f"FLAG_{name.upper()}")
        if env_val is not None:
            return env_val.strip().lower() in ("1", "true", "yes", "on")
        return default_for_unknown

    def all_flags(self) -> dict:
        merged = dict(DEFAULTS)
        merged.update(self.overrides)
        return merged
