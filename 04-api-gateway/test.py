# test_security.py
import requests

BASE_URL = "http://localhost:8000"

def test_api_key():
    # Without key
    r = requests.post(f"{BASE_URL}/ask", json={"question": "test"})
    assert r.status_code == 401, "Should reject without API key"
    
    # With key
    r = requests.post(
        f"{BASE_URL}/ask",
        headers={"X-API-Key": "secret"},
        json={"question": "test"}
    )
    assert r.status_code == 200, "Should accept with valid key"

def test_rate_limit():
    # Send 20 requests
    for i in range(20):
        r = requests.post(
            f"{BASE_URL}/ask",
            headers={"X-API-Key": "secret"},
            json={"question": f"test {i}"}
        )
    
    # Should get 429
    assert r.status_code == 429, "Should rate limit after threshold"

if __name__ == "__main__":
    test_api_key()
    test_rate_limit()
    print("✅ All tests passed")