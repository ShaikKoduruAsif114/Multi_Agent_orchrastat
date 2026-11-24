def parse_ini(text: str) -> dict:
    config = {}
    section = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("["):
            # BUG: brackets kept in the section name
            section = line
            config[section] = {}
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        # BUG: inline comments not stripped
        if section is not None:
            config[section][key.strip()] = value.strip()
    return config

def get_value(config: dict, section: str, key: str, default=None):
    sec = config.get(f"[{section}]", config.get(section))
    if sec is None:
        return default
    return sec.get(key, default)
