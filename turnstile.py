import requests
from typing import Optional

# Cloudflare Turnstile configuration
TURNSTILE_SECRET_KEY = "XXXXXXXXXXXXXXXXXX"  # Change this in production!
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

def verify_turnstile_token(token: str, remote_ip: Optional[str] = None) -> bool:
    """
    Verify a Cloudflare Turnstile token.
    
    Args:
        token: The token from the client
        remote_ip: Optional client IP for additional verification
    
    Returns:
        True if token is valid, False otherwise
    """
    data = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token
    }
    
    if remote_ip:
        data["remoteip"] = remote_ip
    
    try:
        # Use application/x-www-form-urlencoded content type
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(TURNSTILE_VERIFY_URL, data=data, headers=headers, timeout=10)
        
        response.raise_for_status()
        
        result = response.json()
        
        return result.get("success", False)
        
    except (requests.RequestException, ValueError):
        return False 