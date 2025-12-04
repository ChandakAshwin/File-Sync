#!/usr/bin/env python3
"""
Box Token Manager - Handles automatic token refresh
Solves the OAuth token expiration problem by using refresh tokens
"""

import json
import requests
import time
from datetime import datetime, timedelta
import os

class BoxTokenManager:
    """Manages Box OAuth tokens with automatic refresh"""
    
    def __init__(self, credentials_file="box_credentials.json"):
        self.credentials_file = credentials_file
        self.client_id = "r6whd3kssnoijt92niqcuy507dqjcm3z"
        self.client_secret = "RG2WqsC18DjPtbUnvJSHL80k6yJzhm0f"
        self.credentials = None
        self.load_credentials()
    
    def load_credentials(self):
        """Load credentials from file"""
        try:
            with open(self.credentials_file, 'r') as f:
                self.credentials = json.load(f)
            print("✅ Loaded Box credentials from file")
        except FileNotFoundError:
            print("❌ No credentials file found")
            self.credentials = None
    
    def save_credentials(self):
        """Save credentials to file"""
        if self.credentials:
            with open(self.credentials_file, 'w') as f:
                json.dump(self.credentials, f, indent=2)
            print("✅ Credentials saved to file")
    
    def is_token_expired(self):
        """Check if access token is expired or will expire soon"""
        if not self.credentials or 'expires_at' not in self.credentials:
            return True
        
        try:
            expires_at = datetime.fromisoformat(self.credentials['expires_at'])
            # Consider token expired if it expires within 5 minutes
            return datetime.now() >= (expires_at - timedelta(minutes=5))
        except:
            return True
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        if not self.credentials or not self.credentials.get('box_refresh_token'):
            print("❌ No refresh token available")
            return False
        
        print("🔄 Refreshing access token...")
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.credentials['box_refresh_token'],
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        try:
            response = requests.post('https://api.box.com/oauth2/token', data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Update credentials with new tokens
                self.credentials['box_access_token'] = token_data['access_token']
                
                # Update refresh token if provided (Box sometimes provides new ones)
                if 'refresh_token' in token_data:
                    self.credentials['box_refresh_token'] = token_data['refresh_token']
                
                # Calculate and save expiration time
                expires_in = token_data.get('expires_in', 3600)  # Default 1 hour
                expires_at = datetime.now() + timedelta(seconds=expires_in)
                self.credentials['expires_at'] = expires_at.isoformat()
                
                # Save updated credentials
                self.save_credentials()
                
                print(f"✅ Access token refreshed, expires at: {expires_at}")
                return True
            else:
                print(f"❌ Token refresh failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error refreshing token: {e}")
            return False
    
    def get_valid_access_token(self):
        """Get a valid access token, refreshing if necessary"""
        if not self.credentials:
            print("❌ No credentials available")
            return None
        
        # Check if token needs refresh
        if self.is_token_expired():
            print("⏰ Access token expired or expiring soon")
            if not self.refresh_access_token():
                print("❌ Failed to refresh token")
                return None
        
        return self.credentials.get('box_access_token')
    
    def test_connection(self):
        """Test Box connection with current token"""
        token = self.get_valid_access_token()
        if not token:
            return False
        
        try:
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get('https://api.box.com/2.0/users/me', headers=headers)
            
            if response.status_code == 200:
                user_data = response.json()
                print(f"✅ Box connection successful - user: {user_data['name']}")
                return True
            else:
                print(f"❌ Box connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Connection test error: {e}")
            return False
    
    def initial_setup_with_auth_code(self, auth_code):
        """Initial setup with authorization code (run once)"""
        print("🔧 Setting up initial credentials...")
        
        data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': 'http://localhost:8000/admin/connectors/box/oauth/callback'
        }
        
        try:
            response = requests.post('https://api.box.com/oauth2/token', data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Calculate expiration time
                expires_in = token_data.get('expires_in', 3600)
                expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                # Create credentials
                self.credentials = {
                    'box_access_token': token_data['access_token'],
                    'box_refresh_token': token_data.get('refresh_token'),
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'expires_at': expires_at.isoformat()
                }
                
                # Save credentials
                self.save_credentials()
                
                print("✅ Initial setup completed!")
                return True
            else:
                print(f"❌ Setup failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Setup error: {e}")
            return False

def main():
    """Test the token manager"""
    print("🔧 Box Token Manager Test")
    print("=" * 30)
    
    manager = BoxTokenManager()
    
    # Check if we have credentials
    if not manager.credentials:
        print("❌ No credentials found. Run initial setup first.")
        print("\nGet auth code from:")
        print("https://account.box.com/api/oauth2/authorize?response_type=code&client_id=r6whd3kssnoijt92niqcuy507dqjcm3z&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fadmin%2Fconnectors%2Fbox%2Foauth%2Fcallback&state=setup")
        print("\nThen run: python box_token_manager.py setup YOUR_AUTH_CODE")
        return
    
    # Test connection (will auto-refresh if needed)
    print("🔍 Testing Box connection...")
    if manager.test_connection():
        print("🎉 Box Token Manager working perfectly!")
        
        # Show token info
        token = manager.get_valid_access_token()
        print(f"📋 Current token: {token[:20]}...")
        
        if 'expires_at' in manager.credentials:
            expires_at = datetime.fromisoformat(manager.credentials['expires_at'])
            print(f"⏰ Expires at: {expires_at}")
    else:
        print("❌ Token Manager test failed")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 3 and sys.argv[1] == "setup":
        # Initial setup with auth code
        auth_code = sys.argv[2]
        manager = BoxTokenManager()
        success = manager.initial_setup_with_auth_code(auth_code)
        if success:
            print("\n🎉 Setup complete! Now you can use the token manager.")
            manager.test_connection()
        else:
            print("\n❌ Setup failed")
    else:
        # Regular test
        main()