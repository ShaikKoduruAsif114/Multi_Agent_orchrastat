DEFAULTS = {"timeout": 30, "retries": 3, "debug": False}

class Config:
    def __init__(self, **overrides):
        self._values = dict(DEFAULTS)
        self._values.update(overrides)

    def get(self, key, default=None):
        # BUG: raises instead of returning default
        return self._values[key]

    def set(self, key, value):
        # BUG: mutates the global DEFAULTS dict
        DEFAULTS[key] = value
        self._values[key] = value

    def as_dict(self):
        return dict(self._values)
