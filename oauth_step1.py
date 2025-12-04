import os
import sys
import webbrowser
from urllib.parse import urlencode

PROJECT_ROOT = r'C:\Users\Dell\Desktop\local\WokeloFileSync'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from connectors.box.auth import build_authorize_url

# Your Box app credentials (from previous run)
client_id = 'r6whd3kssnoijt92niqcuy507dqjcm3z'
client_secret = 'RG2WqsC18DjPtbUnvJSHL80k6yJzhm0f'
redirect_uri = 'http://localhost:3000/callback'
state = 'box_oauth_setup'

print('🔐 Box OAuth Authentication Setup')
print('=================================')
print()

# Build authorization URL
auth_url = build_authorize_url(
    client_id=client_id,
    redirect_uri=redirect_uri,
    state=state
)

print('📱 AUTHORIZATION URL:')
print(auth_url)
print()

print('🌐 Opening in browser...')
try:
    webbrowser.open(auth_url)
    print('✅ Browser opened successfully')
except Exception as e:
    print(f'❌ Could not open browser: {e}')
    print('💡 Please manually copy the URL above and open it in your browser')

print()
print('👆 NEXT STEPS:')
print('1. Complete authorization in your browser')
print('2. You\'ll be redirected to localhost:3000/callback?code=...')
print('3. Copy the FULL redirect URL from your browser')
print('4. Come back here with that URL')
print()
print('⏳ Waiting for you to complete authorization...')
