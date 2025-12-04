#!/usr/bin/env python3
"""
Run a one-shot indexing + local sync + prune using the Wokelo worker tasks.
"""

import sys
from connectors.box.auth import BoxTokenManager


def run_full_cycle():
    print(' WOKELO FILE SYNC - FULL CYCLE')
    print('=' * 60)

    print('1.  Initializing Box Token Manager...')
    token_manager = BoxTokenManager()
    if not token_manager.credentials:
        print('    No credentials found. Need to run initial setup first.')
        print('   Get fresh auth code and run: python connectors/box/auth.py setup YOUR_CODE')
        return False

    print('2.  Testing Box connection with auto-refresh...')
    if not token_manager.test_connection():
        print('    Box connection failed even after token refresh')
        return False

    print('3.  Running indexing pipeline...')
    sys.path.insert(0, '.')
    from workers.celery_worker_functional import connector_doc_fetching_task

    payload = {
        'connector_credential_pair_id': 1,
        'connector_id': 1,
        'attempt_id': 10,
        'from_beginning': True
    }

    try:
        result = connector_doc_fetching_task(payload)
        print(f'   INDEXING COMPLETED: {result}')
        print('4.  Final status checks (optional)')
        print('\n DONE - Full cycle executed')
        return True
    except Exception as e:
        print(f'   Indexing failed: {e}')
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    ok = run_full_cycle()
    if not ok:
        sys.exit(1)
