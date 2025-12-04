#!/usr/bin/env python3
"""
Box OAuth Authentication Setup

This utility helps you set up OAuth authentication for Box API access.
OAuth tokens can be refreshed automatically, making them perfect for automation.
"""

import os
import sys
import json
import webbrowser
from urllib.parse import urlparse, parse_qs

# Add project to path
PROJECT_ROOT = r'C:\Users\Dell\Desktop\local\WokeloFileSync'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from connectors.box.auth import build_authorize_url, exchange_code_for_tokens_async
import anyio


def setup_oauth():
    """Setup OAuth authentication for Box."""
    print("🔐 Box OAuth Authentication Setup")
    print("=================================")
    print()
    
    # Get Box app credentials
    print("📋 You'll need your Box app credentials from:")
    print("   https://app.box.com/developers/console")
    print()
    
    client_id = input("Enter your Box Client ID: ").strip()
    if not client_id:
        print("❌ Client ID is required")
        return
        
    client_secret = input("Enter your Box Client Secret: ").strip()
    if not client_secret:
        print("❌ Client Secret is required")
        return
    
    # Create redirect URI (using localhost)
    redirect_uri = "http://localhost:3000/callback"
    state = "box_oauth_setup"
    
    print()
    print("🌐 Starting OAuth flow...")
    print(f"   Redirect URI: {redirect_uri}")
    print()
    
    # Build authorization URL
    auth_url = build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state
    )
    
    print("📱 Opening authorization URL in browser...")
    print(f"   URL: {auth_url}")
    print()
    
    # Open browser
    webbrowser.open(auth_url)
    
    print("👆 Complete authorization in your browser, then:")
    print("   1. You'll be redirected to localhost:3000/callback?code=...")
    print("   2. Copy the FULL redirect URL from your browser")
    print("   3. Paste it below")
    print()
    
    # Get authorization code from user
    callback_url = input("Paste the full callback URL here: ").strip()
    if not callback_url:
        print("❌ Callback URL is required")
        return
    
    # Parse the code from callback URL
    try:
        parsed = urlparse(callback_url)
        query_params = parse_qs(parsed.query)
        
        if 'error' in query_params:
            print(f"❌ Authorization error: {query_params['error'][0]}")
            return
            
        if 'code' not in query_params:
            print("❌ No authorization code found in URL")
            return
            
        auth_code = query_params['code'][0]
        print(f"✅ Got authorization code: {auth_code[:20]}...")
        
    except Exception as e:
        print(f"❌ Error parsing callback URL: {e}")
        return
    
    # Exchange code for tokens
    print()
    print("🔄 Exchanging authorization code for tokens...")
    
    try:
        async def get_tokens():
            return await exchange_code_for_tokens_async(
                client_id=client_id,
                client_secret=client_secret,
                code=auth_code,
                redirect_uri=redirect_uri
            )
        
        token_data = anyio.run(get_tokens)
        
        print("✅ Got OAuth tokens successfully!")
        
        # Prepare credentials for BoxTokenManager format
        credentials = {
            "box_access_token": token_data["access_token"],
            "box_refresh_token": token_data["refresh_token"],
            "expires_at": token_data["expires_at"].isoformat(),
            "scope": token_data.get("scope"),
            "token_type": token_data.get("token_type", "Bearer")
        }
        
        # Save credentials
        credentials_file = "box_credentials.json"
        with open(credentials_file, 'w') as f:
            json.dump(credentials, f, indent=2)
        
        print(f"💾 Saved credentials to {credentials_file}")
        
        # Test the credentials
        print()
        print("🧪 Testing OAuth connection...")
        
        from connectors.box.auth import BoxTokenManager
        token_manager = BoxTokenManager()
        
        if token_manager.test_connection():
            print("✅ OAuth authentication successful!")
            print()
            print("🎉 Setup complete! Your automation can now use OAuth.")
            print("   - Tokens will refresh automatically")
            print("   - No more hourly expiration issues")
            print("   - Reliable 24/7 operation")
        else:
            print("❌ OAuth connection test failed")
            
    except Exception as e:
        print(f"❌ Error exchanging code for tokens: {e}")
        return


if __name__ == "__main__":
    setup_oauth()