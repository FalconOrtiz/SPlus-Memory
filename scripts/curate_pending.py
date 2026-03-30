#!/usr/bin/env python3
"""Curate pending facts: enrich domains, promote to committed, remove noise."""
import sqlite3, json, re, os

DB = os.path.join(os.path.dirname(__file__), '..', 'db', 'memory.db')
conn = sqlite3.connect(DB)

DOMAIN_RULES = {
    r'stream|video|youtube|selenium|content|publicar': 'content',
    r'agent|hermes|hermes_agent|leo|nova|aria': 'ai_agents',
    r'memory|memoria|capas|retrieval|embedding': 'memory_system',
    r'deploy|hosting|hostinger|vps|ssh': 'deployment',
    r'google ads|marketing|campaign|ads': 'marketing',
    r'ui|dashboard|interfaz|visual': 'ui',
    r'monitor|health|cron|heartbeat': 'monitoring',
    r'database|sqlite|postgres|schema': 'database',
    r'auth|login|credential|oauth|api.key': 'auth',
    r'automation|pipeline|cron|script': 'automation',
    r'stripe|payment|billing|subscription': 'payments',
    r'linkedin|twitter|x\.com|social': 'social_media',
    r'codigo|code|debug|error|bug': 'development',
}

def detect_domain(text):
    text = (text or '').lower()
    domains = set()
    for pattern, domain in DOMAIN_RULES.items():
        if re.search(pattern, text):
            domains.add(domain)
    return list(domains) if domains else ['general']

rows = conn.execute('''
    SELECT id, summary, raw_content, keywords 
    FROM quantum_facts WHERE status='pending'
''').fetchall()

promoted = 0
enriched = 0
noise = 0

for fid, summ, raw, kw_str in rows:
    raw_text = raw or ''
    
    clean = re.sub(r'[^\w\s]', '', raw_text).strip()
    if len(clean) < 15:
        conn.execute("UPDATE quantum_facts SET status='abandoned' WHERE id=?", (fid,))
        noise += 1
        continue
    
    try:
        kw = json.loads(kw_str) if kw_str else {}
    except:
        kw = {}
    
    current_domains = kw.get('domain', [])
    if not current_domains or current_domains == ['?']:
        detected = detect_domain(raw_text + ' ' + (summ or ''))
        kw['domain'] = detected
        conn.execute("UPDATE quantum_facts SET keywords=? WHERE id=?", (json.dumps(kw), fid))
        
        if summ and '?:?' in summ:
            action = kw.get('action', ['note'])[0] if kw.get('action') else 'note'
            new_summ = f"[COMMITTED] falcon:{action}:{'+'.join(detected)}"
            conn.execute("UPDATE quantum_facts SET summary=? WHERE id=?", (new_summ, fid))
        enriched += 1
    
    conn.execute("UPDATE quantum_facts SET status='committed' WHERE id=?", (fid,))
    promoted += 1

conn.commit()

stats = conn.execute('SELECT status, COUNT(*) FROM quantum_facts GROUP BY status ORDER BY COUNT(*) DESC').fetchall()

print(f'CURATION COMPLETE')
print(f'=================')
print(f'Promoted to committed: {promoted}')
print(f'Domains enriched:      {enriched}')
print(f'Marked as noise:       {noise}')
print()
print('NEW STATUS DISTRIBUTION:')
for s, c in stats:
    print(f'  {s}: {c}')

conn.close()
