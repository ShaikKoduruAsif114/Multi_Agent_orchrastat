import os
import time
import requests
import webbrowser
from dotenv import set_key


def authenticate_github_via_browser() -> str:
    """Trigger a browser popup window for the user to authorize GitHub access.
    
    Uses GitHub OAuth Device Authorization Flow (RFC 8628), the official standard
    used by GitHub CLI and VS Code.
    """
    print("\n" + "=" * 65)
    print("🌐 CONNECT GITHUB VIA BROWSER POPUP")
    print("=" * 65)

    client_id = os.getenv("GITHUB_CLIENT_ID", "178c6fc778cc91e976ea")

    # Step 1: Request Device & User Verification Codes
    try:
        res = requests.post(
            "https://github.com/login/device/code",
            headers={"Accept": "application/json"},
            data={"client_id": client_id, "scope": "repo workflow"},
            timeout=10
        )
        data = res.json()

        if "device_code" not in data:
            # Fallback if device flow registration error
            return prompt_fallback_token()

        device_code = data["device_code"]
        user_code = data["user_code"]
        verification_uri = data.get("verification_uri", "https://github.com/login/device")
        interval = data.get("interval", 5)

        print(f"\n🔑 YOUR AUTHORIZATION CODE: {user_code}")
        print(f"🌐 Opening GitHub authorization popup in your browser...")
        print(f"👉 URL: {verification_uri}\n")

        # Automatically open browser popup window for user
        webbrowser.open(verification_uri)

        print("Waiting for you to click 'Authorize' in your browser window...")

        # Step 2: Poll for Access Token
        poll_url = "https://github.com/login/oauth/access_token"
        while True:
            time.sleep(interval)
            poll_res = requests.post(
                poll_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                },
                timeout=10
            )
            poll_data = poll_res.json()

            if "access_token" in poll_data:
                token = poll_data["access_token"]
                print("\n✅ Successfully authenticated with GitHub via Browser Popup!")
                
                # Save token to .env for future runs
                try:
                    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
                    set_key(env_path, "GITHUB_TOKEN", token)
                    print("💾 Token saved to .env for automatic reuse in future runs.")
                except Exception:
                    pass
                return token

            error = poll_data.get("error")
            if error == "authorization_pending":
                continue
            elif error == "slow_down":
                interval += 5
            elif error == "expired_token":
                print("❌ Authorization session expired. Please try again.")
                return prompt_fallback_token()
            elif error == "access_denied":
                print("❌ Access was denied in browser.")
                return prompt_fallback_token()
            else:
                return prompt_fallback_token()

    except Exception as e:
        print(f"⚠️ Browser authentication error: {str(e)}")
        return prompt_fallback_token()


def prompt_fallback_token() -> str:
    print("\nNo interactive token provided. Proceeding without stored token.")
    return ""

