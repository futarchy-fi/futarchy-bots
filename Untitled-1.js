
'agents',
'client_organizations',
'customer_pain_points',
'devolution_items',
'devolutions',
'documents',
'order_items',
'orders',
'organization_analytics ',
'organization_stats',
'pain_point_tickets',
'pain_points',
'payment_methods',
'products',
'shipments',
'ticket_messages',
'tickets',

{
    code: "42804",
    details: null,
    hint: "You will need to rewrite or cast the expression.",
    message: 'column "condition" is of type devolution_item_condition but expression is of type text'
  }

  {
    code: "23502",
    details: "Failing row contains (944d5239-57f2-43cc-8789-af7beacd5179, 44444444-4444-4444-4444-444444444444, null, Size did not fit, requested, 2025-04-21 15:58:57.711816+00, 2025-04-21 15:58:57.711816+00, null).",
    hint: null,
    message: 'null value in column "user_id" of relation "devolutions" violates not-null constraint'
  }
  
  TypeError: Cannot read properties of undefined (reading 'bodyUsed')
    at #respond (https://deno.land/std@0.204.0/http/server.ts:223:20)
    at eventLoopTick (ext:core/01_core.js:168:7)

  

curl -X POST \
  https://oixhswajesofpwmgxyla.supabase.co/functions/v1/return-order \
  -H "Content-Type: application/json" \
  -d '{
        "orderId": "44444444-4444-4444-4444-444444444444",
        "reason": "Size did not fit",
        "items": [
          {
            "orderItemId": "55555555-5555-5555-5555-555555555555",
            "quantity": 1,
            "condition": "unopened",
            "reasonDetail": "Too small"
          }
        ]
      }'
➜  ~ curl -X POST \
  https://oixhswajesofpwmgxyla.supabase.co/functions/v1/return-order \
  -H "Content-Type: application/json" \
  -d '{
        "orderId": "44444444-4444-4444-4444-444444444444",
        "userId": "37973541-022f-4a12-9bf2-db36c2edd8e5",
        "reason": "Size did not fit",
        "items": [
          {
            "orderItemId": "55555555-5555-5555-5555-555555555555",
            "quantity": 1,
            "condition": "unopened",
            "reasonDetail": "Too small"
          }
        ]
      }'

{"success":false,"error":"Expected double-quoted property name in JSON at position 121 (line 3 column 61)"}%

{
    code: "22P02",
    details: null,
    hint: null,
    message: 'invalid input syntax for type uuid: ""'
  }
  