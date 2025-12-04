#!/usr/bin/env python3
"""
Box JWT Authentication Utility

This utility manages JWT-based authentication for Box API access.
It provides persistent, non-expiring authentication for automation tasks.
"""

import os
import sys
import json
from pathlib import Path

# Add project to path
PROJECT_ROOT = r'C:\Users\Dell\Desktop\local\WokeloFileSync'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from connectors.box.auth import BoxJWTAuth


class BoxJWTAuthManager:
    """Manages Box JWT authentication from config file."""
    
    def __init__(self, config_file: str = "box_jwt_config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self._auth_manager = None
    
    def load_config(self) -> dict:
        """Load JWT configuration from file."""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(
                f"Box JWT config file not found: {self.config_file}\n"
                f"Please copy box_jwt_config_template.json to {self.config_file} "
                f"and fill in your Box app details."
            )
        
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def get_auth_manager(self) -> BoxJWTAuth:
        """Get or create the JWT auth manager."""
        if not self._auth_manager:
            app_settings = self.config['boxAppSettings']
            app_auth = app_settings['appAuth']
            
            self._auth_manager = BoxJWTAuth(
                client_id=app_settings['clientID'],
                client_secret=app_settings['clientSecret'],
                private_key=app_auth['privateKey'],
                private_key_passphrase=app_auth.get('passphrase')
            )
        
        return self._auth_manager
    
    def get_access_token(self) -> str:
        """Get a valid access token."""
        auth_manager = self.get_auth_manager()
        return auth_manager.get_access_token()
    
    def test_connection(self) -> bool:
        """Test the JWT authentication."""
        try:
            auth_manager = self.get_auth_manager()
            return auth_manager.test_connection()
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False


def main():
    """Test JWT authentication setup."""
    print("🔐 Box JWT Authentication Test")
    print("=============================")
    print()
    
    try:
        auth_manager = BoxJWTAuthManager()
        print("✅ Config file loaded successfully")
        
        print("🧪 Testing connection...")
        if auth_manager.test_connection():
            print("✅ JWT authentication successful!")
            
            token = auth_manager.get_access_token()
            print(f"🎫 Access token: {token[:20]}...")
            
            print()
            print("🎉 Your Box JWT authentication is working!")
            print("   The automation system can now use this for persistent access.")
            
        else:
            print("❌ JWT authentication failed!")
            print("   Check your config file and Box app settings.")
            
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print()
        print("📋 To set up JWT authentication:")
        print("1. Copy box_jwt_config_template.json to box_jwt_config.json")
        print("2. Fill in your Box app details from Developer Console")
        print("3. Run this script again to test")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()