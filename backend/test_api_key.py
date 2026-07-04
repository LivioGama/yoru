#!/usr/bin/env python3
"""Simple test script to verify API key functionality."""

import hashlib
import secrets
import requests
import json

# Configuration
API_BASE = "http://localhost:8002"
API_KEY_PREFIX = "yoru_pk_"

def generate_test_api_key():
    """Generate a test API key in the same format as the backend."""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    key_prefix = raw[len(API_KEY_PREFIX):len(API_KEY_PREFIX) + 8]
    return raw, key_hash, key_prefix

def test_api_key_endpoint():
    """Test the API key creation endpoint."""
    # First, we need to authenticate to get a session
    # This is a placeholder - in real testing, you'd authenticate first
    print("API Key Test Script")
    print("=" * 50)
    
    # Generate a test key to show the format
    raw, key_hash, key_prefix = generate_test_api_key()
    print(f"Generated test API key:")
    print(f"  Raw: {raw}")
    print(f"  Hash: {key_hash}")
    print(f"  Prefix: {key_prefix}")
    print()
    
    print("To test the API key endpoints:")
    print("1. Start the backend server: cd backend && make restart-backend")
    print("2. Authenticate via the dashboard or CLI to get a session")
    print("3. Use curl to test the endpoints:")
    print()
    print(f"  # Create an API key")
    print(f"  curl -X POST {API_BASE}/auth/api-keys \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -H 'Cookie: rcpt_session=<your_session>' \\")
    print(f"    -d '{{\"label\": \"Test key\"}}'")
    print()
    print(f"  # List API keys")
    print(f"  curl -X GET {API_BASE}/auth/api-keys \\")
    print(f"    -H 'Cookie: rcpt_session=<your_session>'")
    print()
    print(f"  # Use API key to authenticate")
    print(f"  curl -X GET {API_BASE}/auth/session/me \\")
    print(f"    -H 'X-API-Key: {raw}'")
    print()

if __name__ == "__main__":
    test_api_key_endpoint()
