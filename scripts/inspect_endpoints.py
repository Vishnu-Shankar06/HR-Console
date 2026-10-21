import json

with open('scripts/openapi.json', encoding='utf-8') as f:
    d = json.load(f)

endpoints = [
    '/api/v1/documents/upload',
    '/api/v1/documents/{document_id}',
    '/api/v1/documents/{document_id}/status',
    '/api/v1/documents/{document_id}/template-extraction',
    '/api/v1/documents/{document_id}/template',
    '/api/v1/documents/{document_id}/key-fields',
    '/api/v1/documents/{document_id}/metadata',
    '/api/v1/documents/{document_id}/chunks',
    '/api/v1/retrieve',
    '/api/v1/retrieve/documents/search',
    '/api/v1/chat',
    '/api/v1/repositories'
]

for ep in endpoints:
    if ep in d.get('paths', {}):
        print(f"\n==================== {ep} ====================")
        for method, spec in d['paths'][ep].items():
            print(f"[{method.upper()}] Summary: {spec.get('summary')}")
            print(f"Description: {spec.get('description', '')[:200]}")
            params = spec.get('parameters', [])
            if params:
                print("Parameters:")
                for p in params:
                    print(f"  - {p.get('name')} in {p.get('in')} (required: {p.get('required')})")
            rb = spec.get('requestBody', {})
            if rb:
                content = rb.get('content', {})
                for ct, s in content.items():
                    print(f"Request Body [{ct}]:")
                    print(json.dumps(s.get('schema', {}), indent=4))
