import warnings; warnings.filterwarnings('ignore')
import os; os.environ.setdefault('HAEHAN_AGENT_WS_ENABLED','false')
from ai_orchestrator.browser_tool.site_compliance_policy import evaluate_site_compliance
from ai_orchestrator.browser_tool.server_browser_boundary_policy import evaluate_server_browser_allowed

cases = [
    ('g2b_public_readonly', 'www.g2b.go.kr', 'read'),
    ('g2b_public_readonly', 'www.g2b.go.kr', 'navigate'),
    ('g2b', 'www.g2b.go.kr', 'read'),
    ('public_procurement', 'www.g2b.go.kr', 'read'),
    ('g2b_login', 'www.g2b.go.kr', 'submit'),
    ('restricted_financial', 'www.ibk.co.kr', 'read'),
    ('restricted_government', 'www.hometax.go.kr', 'read'),
    ('unknown_public', 'unknown.go.kr', 'read'),
]
for cat, dom, op in cases:
    payload = {'site_category': cat, 'target_domain': dom, 'operation_type': op}
    try:
        comp = evaluate_site_compliance(payload)
        bound = evaluate_server_browser_allowed(payload)
        print(f"RESULT|{cat}|{op}|decision={comp.get('compliance_decision','?')}|server_allowed={bound.get('server_browser_allowed','?')}|execution_loc={bound.get('execution_location_required','?')}")
    except Exception as e:
        print(f"ERROR|{cat}|{op}|{type(e).__name__}:{e}")
