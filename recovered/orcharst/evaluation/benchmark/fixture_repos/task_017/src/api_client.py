class ApiClient:
    def __init__(self, session, base_url="https://api.example.com"):
        self.session = session
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, params=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        # BUG: params passed positionally into headers slot
        return self.session.request("GET", url, params)

    def post(self, path: str, json_body=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        # BUG: json_body never forwarded
        return self.session.request("POST", url)

    def delete(self, path: str):
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self.session.request("DELETE", url)
