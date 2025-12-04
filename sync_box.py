import sys
import os
sys.path.insert(0, r'C:\Users\Dell\Desktop\local\WokeloFileSync')

# Set up environment
os.environ['BOX_DEVELOPER_TOKEN'] = '8LmqQBEXKa5IrFJ3CuwtQA85Nw8se9uC'

print('Starting Box file sync...')

try:
    from infra.storage.local import LocalStorage
    
    # Initialize storage with your token
    storage = LocalStorage(access_token='8LmqQBEXKa5IrFJ3CuwtQA85Nw8se9uC')
    
    # Run sync - this will:
    # 1. Check Box for current files
    # 2. Compare with local storage  
    # 3. Download new/updated files
    # 4. Clean up deleted files automatically
    result = storage.sync_all_documents()
    
    print('Sync completed successfully!')
    print(f'Results:')
    print(f'  Total files: {result["total"]}')
    print(f'  Downloaded: {result["downloaded"]}')
    print(f'  Updated: {result["updated"]}')
    print(f'  Skipped: {result["skipped"]}')
    print(f'  Errors: {result["errors"]}')
    
    # Also run cleanup to remove orphaned files
    orphaned = storage.cleanup_orphaned_files()
    if orphaned > 0:
        print(f'Cleaned up {orphaned} orphaned local files')
    else:
        print('No orphaned files to clean up')
        
except Exception as e:
    print(f'Sync failed: {e}')
    import traceback
    traceback.print_exc()
