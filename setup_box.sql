-- Setup Box integration for WokeloFileSync
-- Insert credential with developer token
INSERT INTO credential (credential_json) 
VALUES ('{"access_token":"8LmqQBEXKa5IrFJ3CuwtQA85Nw8se9uC","client_id":"r6whd3kssnoijt92niqcuy507dqjcm3z","client_secret":"RG2WqsC18DjPtbUnvJSHL80k6yJzhm0f","token_type":"developer_token"}')
RETURNING id;

-- Insert Box connector
INSERT INTO connector (name, source) 
VALUES ('box-connector', 'box') 
RETURNING id;

-- Insert connector-credential pair (use the IDs from above)
-- Note: You'll need to update this with the actual IDs returned above
INSERT INTO connector_credential_pair (name, connector_id, credential_id, status) 
VALUES ('my-box-pair', 
        (SELECT id FROM connector WHERE name = 'box-connector'), 
        (SELECT id FROM credential WHERE credential_json::text LIKE '%8LmqQBEXKa5IrFJ3CuwtQA85Nw8se9uC%'), 
        'ACTIVE') 
RETURNING id;

-- Show the created entries
SELECT 'Credential ID:' as label, id as value FROM credential WHERE credential_json::text LIKE '%8LmqQBEXKa5IrFJ3CuwtQA85Nw8se9uC%'
UNION ALL
SELECT 'Connector ID:', id FROM connector WHERE name = 'box-connector'
UNION ALL  
SELECT 'CCPair ID:', id FROM connector_credential_pair WHERE name = 'my-box-pair';