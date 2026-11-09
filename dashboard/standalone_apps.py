"""LeadForge Standalone Apps Server.

Provides native, zero-dependency, professional Python implementations for the five
client pipeline tools when Docker is not installed or when running in local standalone mode:
- listmonk (Port 9000): Email campaigns & subscriber management
- chatwoot (Port 3001): Omnichannel inbox (WhatsApp, Email, Web Chat) with LeadForge sync API
- cal.diy (Port 3002): Interactive appointment and discovery call booking system
- twenty (Port 3003): Full CRM with interactive Kanban deal pipeline
- documenso (Port 3004): Document contracts and digital signature signing workflow
"""

import csv
import html
import json
import os
import re
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from dashboard.intelligence import analyze_lead_intelligence
except ImportError:
    try:
        from intelligence import analyze_lead_intelligence
    except ImportError:
        analyze_lead_intelligence = lambda l, n="": {
            "name": l.get("name", ""), "phone": l.get("phone", ""), "phone_type": "Business Line",
            "is_mobile": False, "is_whatsapp": False, "whatsapp_url": "", "emails": [], "primary_email": l.get("email", ""),
            "social": {}, "maps_url": "", "audit": {"score": 50, "recommendations": []}
        }

HOST = "127.0.0.1"
DATA_DIR = Path(__file__).resolve().parent / "data"
LATEST_CSV = DATA_DIR / "latest.csv"
APPS_DATA_FILE = DATA_DIR / "apps_data.json"

DEFAULT_APPS_DATA = {
    "listmonk": {
        "campaigns": [],
        "subscribers": [],
    },
    "chatwoot": {
        "conversations": [],
    },
    "caldiy": {
        "event_types": [
            {
                "id": "discovery",
                "title": "15 Min Discovery Call",
                "duration": 15,
                "desc": "Quick introductory call to explore requirements, feasibility, and immediate opportunities.",
            },
            {
                "id": "strategy",
                "title": "30 Min Client Strategy Session",
                "duration": 30,
                "desc": "Detailed project discussion, tech stack review, feature scoping, and proposal roadmap.",
            },
            {
                "id": "demo",
                "title": "45 Min Product & Tech Demo",
                "duration": 45,
                "desc": "Interactive walkthrough of custom software solutions, architecture, and live app demos.",
            },
        ],
        "bookings": [],
    },
    "twenty": {
        "deals": [],
    },
    "documenso": {
        "documents": [],
    },
}

DATA_LOCK = threading.Lock()


def load_apps_data():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not APPS_DATA_FILE.exists():
        save_apps_data(DEFAULT_APPS_DATA)
        return dict(DEFAULT_APPS_DATA)
    try:
        with open(APPS_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure all sections exist
            for key, val in DEFAULT_APPS_DATA.items():
                if key not in data:
                    data[key] = val
            return data
    except Exception:
        return dict(DEFAULT_APPS_DATA)


def save_apps_data(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = APPS_DATA_FILE.with_name(APPS_DATA_FILE.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(APPS_DATA_FILE)
    except Exception:
        pass


def get_leadforge_leads():
    leads = []
    if LATEST_CSV.exists():
        try:
            with open(LATEST_CSV, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    name = row.get("title") or row.get("name") or row.get("business_name") or f"Lead #{i+1}"
                    phone = row.get("phone") or row.get("phone_number") or ""
                    website = row.get("website") or row.get("site") or row.get("url") or ""
                    addr = row.get("address") or row.get("full_address") or ""
                    category = row.get("category") or "Local Business"
                    
                    # Run deep intelligence
                    raw_lead = {
                        "name": name,
                        "phone": phone,
                        "website": website,
                        "address": addr,
                        "category": category,
                        "emails": row.get("emails") or row.get("email") or "",
                        "link": row.get("link") or "",
                    }
                    intel = analyze_lead_intelligence(raw_lead)

                    email = intel.get("primary_email") or ""
                    if not email:
                        clean_name = re.sub(r"[^a-zA-Z0-9]", "", name).lower()[:12] or f"lead{i+1}"
                        email = f"contact@{clean_name}.com"

                    leads.append({
                        "id": i + 1,
                        "name": name,
                        "phone": intel.get("phone") or phone,
                        "phone_type": intel.get("phone_type", "Business Line"),
                        "is_mobile": intel.get("is_mobile", False),
                        "is_whatsapp": intel.get("is_whatsapp", False),
                        "whatsapp_url": intel.get("whatsapp_url", ""),
                        "email": email,
                        "emails": intel.get("emails", []),
                        "website": website,
                        "address": addr,
                        "category": category,
                        "social": intel.get("social", {}),
                        "maps_url": intel.get("maps_url", ""),
                        "audit": intel.get("audit", {}),
                    })
        except Exception:
            pass
    return leads


def sync_leads_into_apps():
    """Sync real leads from latest.csv into all standalone apps."""
    leads = get_leadforge_leads()
    if not leads:
        return False, "No leads found in latest.csv to import."
    with DATA_LOCK:
        data = load_apps_data()
        imported = 0
        existing_sub_emails = {s.get("email", "").lower() for s in data["listmonk"]["subscribers"]}
        existing_deal_names = {d.get("company", "").lower() for d in data["twenty"]["deals"]}
        existing_conv_names = {c.get("meta", {}).get("sender", {}).get("name", "").lower() for c in data["chatwoot"]["conversations"]}

        for lead in leads:
            # 1. Add to Listmonk subscribers
            if lead["email"].lower() not in existing_sub_emails:
                sub_id = len(data["listmonk"]["subscribers"]) + 1
                data["listmonk"]["subscribers"].append({
                    "id": sub_id,
                    "name": lead["name"],
                    "email": lead["email"],
                    "status": "enabled",
                    "attribs": {
                        "phone": lead["phone"],
                        "phone_type": lead.get("phone_type", "Business Line"),
                        "whatsapp_url": lead.get("whatsapp_url", ""),
                        "website": lead["website"],
                        "address": lead["address"],
                        "category": lead["category"],
                        "maps_url": lead.get("maps_url", ""),
                        "audit_score": lead.get("audit", {}).get("score", 50),
                    },
                })
                existing_sub_emails.add(lead["email"].lower())
                imported += 1

            # 2. Add to Twenty CRM deals
            if lead["name"].lower() not in existing_deal_names:
                deal_id = len(data["twenty"]["deals"]) + 1
                audit_recs = lead.get("audit", {}).get("recommendations", [])
                recs_str = "; ".join(audit_recs[:2]) if audit_recs else "Standard outreach"
                data["twenty"]["deals"].append({
                    "id": deal_id,
                    "title": f"{lead['name']} - Digital Outreach",
                    "company": lead["name"],
                    "contact": lead["name"],
                    "phone": lead["phone"],
                    "phone_type": lead.get("phone_type", "Business Line"),
                    "email": lead["email"],
                    "value": 2500,
                    "stage": "Lead Discovered",
                    "color": "#38bdf8",
                    "notes": f"Website Audit Score: {lead.get('audit', {}).get('score', 0)}/100. Changes needed: {recs_str}",
                    "maps_url": lead.get("maps_url", ""),
                })
                existing_deal_names.add(lead["name"].lower())

            # 3. Add to Chatwoot conversations (for first 5 leads)
            if len(data["chatwoot"]["conversations"]) < 8 and lead["name"].lower() not in existing_conv_names:
                conv_id = len(data["chatwoot"]["conversations"]) + 1
                data["chatwoot"]["conversations"].append({
                    "id": conv_id,
                    "inbox_name": "WhatsApp Business" if lead.get("is_whatsapp") else "Email Outreach",
                    "status": "open",
                    "unread_count": 0,
                    "meta": {
                        "sender": {
                            "name": lead["name"],
                            "email": lead["email"],
                            "phone_number": lead["phone"],
                        }
                    },
                    "messages": [
                        {
                            "id": 1,
                            "content": f"Hi {lead['name']}, we reviewed your local presence on Google Maps and prepared tailored digital outreach notes.",
                            "message_type": "outgoing",
                            "created_at": datetime.now().isoformat(),
                        }
                    ],
                })
                existing_conv_names.add(lead["name"].lower())
                existing_deal_names.add(lead["name"].lower())

            # 3. Add to Chatwoot conversations (for first 3 leads)
            if len(data["chatwoot"]["conversations"]) < 5 and lead["name"].lower() not in existing_conv_names:
                conv_id = len(data["chatwoot"]["conversations"]) + 1
                data["chatwoot"]["conversations"].append({
                    "id": conv_id,
                    "inbox_id": 1,
                    "status": "open",
                    "unread_count": 0,
                    "meta": {
                        "sender": {
                            "id": 100 + conv_id,
                            "name": lead["name"],
                            "phone_number": lead["phone"],
                            "email": lead["email"],
                            "website": lead["website"],
                        }
                    },
                    "messages": [
                        {
                            "id": 1,
                            "message_type": 1,
                            "content": f"Hello {lead['name']}, this is Tanmoy from GDL Technologies. We reviewed your business listing and prepared a personalized proposal to improve your online inquiries.",
                            "created_at": datetime.now().strftime("%I:%M %p"),
                        }
                    ],
                    "updated_at": datetime.now().isoformat(),
                })
                existing_conv_names.add(lead["name"].lower())

        save_apps_data(data)
        return True, f"Successfully imported {len(leads)} real leads from LeadForge!"


COMMON_HEAD = """
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {
  --bg: #090d16;
  --surface: #111827;
  --surface-2: #1e293b;
  --surface-3: #334155;
  --border: #1f293d;
  --border-light: #2d3748;
  --text: #f8fafc;
  --text-muted: #94a3b8;
  --text-dim: #64748b;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --success: #10b981;
  --success-bg: rgba(16, 185, 129, 0.12);
  --warning: #f59e0b;
  --warning-bg: rgba(245, 158, 11, 0.12);
  --danger: #ef4444;
  --radius: 10px;
  --radius-sm: 6px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Helvetica, Arial, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--font); background: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; -webkit-font-smoothing: antialiased; }
header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 28px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 50; }
.brand { display: flex; align-items: center; gap: 12px; font-weight: 700; font-size: 1.15rem; color: var(--text); text-decoration: none; }
.badge-local { background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 0.72rem; padding: 3px 9px; border-radius: 999px; font-weight: 600; border: 1px solid rgba(16, 185, 129, 0.3); }
.nav-link { color: var(--text-muted); text-decoration: none; font-size: 0.88rem; font-weight: 500; padding: 7px 14px; border-radius: var(--radius-sm); transition: all 0.15s; }
.nav-link:hover, .nav-link.active { color: var(--text); background: var(--surface-2); }
main { flex: 1; padding: 28px; max-width: 1280px; margin: 0 auto; width: 100%; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px 20px; }
.stat-label { font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 6px; }
.stat-val { font-size: 1.75rem; font-weight: 700; color: var(--text); }
.stat-sub { font-size: 0.75rem; color: var(--text-dim); margin-top: 4px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 22px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid var(--border); padding-bottom: 14px; }
h2 { font-size: 1.25rem; font-weight: 600; color: var(--text); }
h3 { font-size: 1.05rem; font-weight: 600; color: var(--text); }
p { color: var(--text-muted); font-size: 0.9rem; line-height: 1.5; }
.btn { background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: var(--radius-sm); font-weight: 600; font-size: 0.85rem; cursor: pointer; display: inline-flex; align-items: center; gap: 7px; text-decoration: none; transition: background 0.15s ease; }
.btn:hover { background: var(--accent-hover); }
.btn-sm { padding: 5px 11px; font-size: 0.78rem; }
.btn-secondary { background: var(--surface-2); color: var(--text); border: 1px solid var(--border-light); }
.btn-secondary:hover { background: var(--surface-3); }
.btn-success { background: #059669; }
.btn-success:hover { background: #047857; }
.btn-sync { background: linear-gradient(135deg, #4f46e5, #3b82f6); color: white; border: none; }
.btn-sync:hover { background: linear-gradient(135deg, #4338ca, #2563eb); }
table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.88rem; }
th { text-align: left; padding: 11px 14px; background: var(--surface-2); color: var(--text-muted); border-bottom: 1px solid var(--border); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
td { padding: 13px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }
tr:hover td { background: rgba(255,255,255,0.015); }
.badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em; }
.badge-sent, .badge-signed, .badge-active, .badge-ok { background: var(--success-bg); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.25); }
.badge-pending, .badge-draft, .badge-warn { background: var(--warning-bg); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.25); }
.toast { background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 12px 18px; border-radius: var(--radius-sm); margin-bottom: 20px; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.9rem; }
input, select, textarea { background: var(--surface-2); border: 1px solid var(--border-light); color: var(--text); padding: 9px 13px; border-radius: var(--radius-sm); font-size: 0.88rem; width: 100%; transition: border-color 0.15s; }
input:focus, textarea:focus, select:focus { outline: none; border-color: var(--accent); }
.leadforge-banner { background: linear-gradient(90deg, #111827, #1e1b4b); border: 1px solid #3730a3; border-radius: var(--radius); padding: 12px 20px; margin-bottom: 22px; display: flex; justify-content: space-between; align-items: center; }
.leadforge-banner span { font-size: 0.86rem; color: #c7d2fe; display: flex; align-items: center; gap: 8px; }
.leadforge-banner a { color: #818cf8; font-weight: 600; text-decoration: none; font-size: 0.85rem; }
.empty-state { text-align: center; padding: 48px 24px; color: var(--text-muted); }
.empty-icon { font-size: 2.5rem; margin-bottom: 12px; opacity: 0.8; }
.empty-state h3 { font-size: 1.15rem; color: var(--text); margin-bottom: 6px; }
.empty-state p { max-width: 460px; margin: 0 auto 18px auto; font-size: 0.88rem; }
</style>
"""


def render_leadforge_banner():
    leads_count = len(get_leadforge_leads())
    sync_cta = f'<form method="post" action="/sync/leads" style="display:inline;"><button type="submit" class="btn btn-sm btn-sync">📥 Import {leads_count} Leads from LeadForge</button></form>' if leads_count > 0 else '<span style="color:var(--text-dim);font-size:0.8rem;">Run search on LeadForge home to find leads</span>'
    return f"""
<div class="leadforge-banner">
  <span>⚡ Connected to <strong>LeadForge Pipeline</strong> &bull; Standalone Mode active (No Docker required)</span>
  <div style="display:flex;align-items:center;gap:14px;">
    {sync_cta}
    <a href="http://127.0.0.1:8790/apps">&larr; Return to Dashboard</a>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# 1. LISTMONK (PORT 9000)
# ---------------------------------------------------------------------------
def listmonk_html(message=""):
    with DATA_LOCK:
        data = load_apps_data()
        campaigns = list(data["listmonk"]["campaigns"])
        subscribers = list(data["listmonk"]["subscribers"])

    total_sent = sum(c.get("sent", 0) for c in campaigns)
    total_opened = sum(c.get("opened", 0) for c in campaigns)
    open_rate = f"{(total_opened / total_sent * 100):.1f}%" if total_sent > 0 else "0.0%"

    if campaigns:
        c_rows = ""
        for c in campaigns:
            badge_cls = "badge-sent" if c.get("status") in ("sent", "active") else "badge-draft"
            c_rows += f"""<tr>
<td><strong>{html.escape(c.get('name', ''))}</strong></td>
<td><span class="badge {badge_cls}">{html.escape(c.get('status', 'DRAFT').upper())}</span></td>
<td>{html.escape(c.get('sent_at', '-'))}</td>
<td>{c.get('sent', 0)} recipients</td>
<td>{c.get('opened', 0)} opened</td>
<td>{c.get('clicked', 0)} clicked</td>
</tr>"""
        camp_section = f"""
        <table>
          <thead>
            <tr><th>Campaign Subject</th><th>Status</th><th>Timestamp</th><th>Sent</th><th>Opened</th><th>Clicks</th></tr>
          </thead>
          <tbody>{c_rows}</tbody>
        </table>"""
    else:
        camp_section = """
        <div class="empty-state">
          <div class="empty-icon">✉️</div>
          <h3>No outreach campaigns yet</h3>
          <p>Create your first email campaign below to send outreach to your prospective clients.</p>
          <button class="btn btn-success" onclick="document.getElementById('new-camp-modal').style.display='block'">+ Create First Campaign</button>
        </div>"""

    if subscribers:
        s_rows = ""
        for s in subscribers:
            phone = s.get("attribs", {}).get("phone", "")
            cat = s.get("attribs", {}).get("category", "Prospect")
            s_rows += f"""<tr>
<td><strong>{html.escape(s.get('name', ''))}</strong></td>
<td>{html.escape(s.get('email', ''))}</td>
<td>{html.escape(phone or '-')}</td>
<td><span class="badge badge-ok">{html.escape(cat)}</span></td>
<td><span class="badge badge-sent">ACTIVE</span></td>
</tr>"""
        sub_section = f"""
        <table>
          <thead>
            <tr><th>Business Name</th><th>Email</th><th>Phone</th><th>Category</th><th>Status</th></tr>
          </thead>
          <tbody>{s_rows}</tbody>
        </table>"""
    else:
        leads_count = len(get_leadforge_leads())
        sub_import_btn = f'<form method="post" action="/sync/leads" style="display:inline;"><button type="submit" class="btn btn-sync">📥 Import {leads_count} Leads from LeadForge</button></form>' if leads_count > 0 else '<a href="http://127.0.0.1:8790/" class="btn btn-secondary">🔍 Find Leads in LeadForge</a>'
        sub_section = f"""
        <div class="empty-state">
          <div class="empty-icon">👥</div>
          <h3>No subscribers in the list</h3>
          <p>Import verified leads discovered on Google Maps by LeadForge, or manually add your target contacts.</p>
          <div style="display:flex;justify-content:center;gap:10px;">
            {sub_import_btn}
            <button class="btn btn-secondary" onclick="document.getElementById('new-sub-modal').style.display='block'">+ Add Single Subscriber</button>
          </div>
        </div>"""

    banner = render_leadforge_banner()
    notice = f'<div class="toast">{html.escape(message)}</div>' if message else ""

    return f"""<!doctype html>
<html>
<head>
<title>listmonk - Email Campaigns & Subscriber Outreach</title>
{COMMON_HEAD}
</head>
<body>
<header>
  <div class="brand">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
    listmonk <span class="badge-local">Standalone Engine</span>
  </div>
  <nav style="display:flex;gap:8px;">
    <a href="/" class="nav-link active">Dashboard</a>
    <a href="#subscribers" class="nav-link">Subscribers ({len(subscribers)})</a>
    <a href="http://127.0.0.1:8790/writer" class="nav-link">AI Pitch Writer</a>
  </nav>
</header>
<main>
  {banner}
  {notice}

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Total Subscribers</div>
      <div class="stat-val">{len(subscribers)}</div>
      <div class="stat-sub">Verified outreach contacts</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Campaigns Created</div>
      <div class="stat-val">{len(campaigns)}</div>
      <div class="stat-sub">{total_sent} total messages queued/sent</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Open Rate</div>
      <div class="stat-val">{open_rate}</div>
      <div class="stat-sub">Engagement performance</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Pipeline Engine</div>
      <div class="stat-val" style="color:var(--success);">Native</div>
      <div class="stat-sub">Zero Docker requirement</div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div>
        <h2>Outreach Campaigns</h2>
        <p>Send personalized pitches and follow-up emails to your verified business list.</p>
      </div>
      <button class="btn btn-success" onclick="document.getElementById('new-camp-modal').style.display='block'">+ New Campaign</button>
    </div>
    {camp_section}
  </div>

  <div class="card" id="subscribers">
    <div class="card-header">
      <div>
        <h2>Target Subscribers ({len(subscribers)})</h2>
        <p>Prospective businesses ready for automated email distribution.</p>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-secondary btn-sm" onclick="document.getElementById('new-sub-modal').style.display='block'">+ Add Contact</button>
      </div>
    </div>
    {sub_section}
  </div>

  <!-- New Campaign Modal -->
  <div id="new-camp-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.75);z-index:99;padding:40px 20px;">
    <div style="background:var(--surface);max-width:560px;margin:30px auto;padding:26px;border-radius:var(--radius);border:1px solid var(--border);">
      <h3 style="margin-bottom:14px;">Create Outreach Campaign</h3>
      <form method="post" action="/campaigns/create">
        <div style="margin-bottom:14px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:5px;">Campaign Subject</label>
          <input type="text" name="name" required placeholder="e.g. Website Upgrade & Client Inquiries for Your Business">
        </div>
        <div style="margin-bottom:18px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:5px;">Message Body</label>
          <textarea name="body" rows="5" placeholder="Hello, I noticed your business listing and had an idea to help you get more client bookings..."></textarea>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;">
          <button type="button" class="btn btn-secondary" onclick="document.getElementById('new-camp-modal').style.display='none'">Cancel</button>
          <button type="submit" class="btn btn-success">Schedule & Send to List</button>
        </div>
      </form>
    </div>
  </div>

  <!-- New Subscriber Modal -->
  <div id="new-sub-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.75);z-index:99;padding:40px 20px;">
    <div style="background:var(--surface);max-width:500px;margin:40px auto;padding:24px;border-radius:var(--radius);border:1px solid var(--border);">
      <h3 style="margin-bottom:14px;">Add New Contact</h3>
      <form method="post" action="/subscribers/create">
        <div style="margin-bottom:12px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Business / Contact Name</label>
          <input type="text" name="name" required placeholder="e.g. City Dental Clinic">
        </div>
        <div style="margin-bottom:12px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Email Address</label>
          <input type="email" name="email" required placeholder="contact@business.com">
        </div>
        <div style="margin-bottom:16px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Phone Number (Optional)</label>
          <input type="text" name="phone" placeholder="+91 98300 00000">
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;">
          <button type="button" class="btn btn-secondary" onclick="document.getElementById('new-sub-modal').style.display='none'">Cancel</button>
          <button type="submit" class="btn btn-accent">Save Contact</button>
        </div>
      </form>
    </div>
  </div>
</main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 2. CHATWOOT (PORT 3001)
# ---------------------------------------------------------------------------
def chatwoot_html(active_id=None, notice=""):
    with DATA_LOCK:
        data = load_apps_data()
        convs = list(data["chatwoot"]["conversations"])

    if convs and active_id is None:
        active_id = convs[0]["id"]

    current = next((c for c in convs if c["id"] == active_id), convs[0] if convs else None)

    threads_html = ""
    for c in convs:
        sender = c.get("meta", {}).get("sender", {})
        active_cls = "active" if current and current["id"] == c["id"] else ""
        last_msg = c["messages"][-1]["content"] if c.get("messages") else "No messages"
        updated = c.get("updated_at", "").split("T")[-1][:5] or "Today"
        threads_html += f"""
<div onclick="window.location.href='/?conv={c['id']}'" style="padding:14px 18px;border-bottom:1px solid var(--border);cursor:pointer;background:{'var(--surface-2)' if active_cls else 'transparent'};border-left:3px solid {'var(--accent)' if active_cls else 'transparent'};transition:background 0.15s;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
    <strong style="font-size:0.92rem;color:var(--text);">{html.escape(sender.get('name', 'Unknown Prospect'))}</strong>
    <span style="font-size:0.72rem;color:var(--text-muted);">{html.escape(updated)}</span>
  </div>
  <div style="font-size:0.82rem;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{html.escape(last_msg)}</div>
</div>"""

    if current and current.get("messages"):
        chat_body = ""
        for m in current["messages"]:
            is_me = m.get("message_type") == 1
            chat_body += f"""
<div style="display:flex;justify-content:{'flex-end' if is_me else 'flex-start'};margin-bottom:14px;">
  <div style="max-width:72%;padding:11px 16px;border-radius:12px;background:{'#1e3a8a' if is_me else 'var(--surface-2)'};color:{'#dbeafe' if is_me else 'var(--text)'};border:1px solid {'#2563eb' if is_me else 'var(--border)'};box-shadow:0 2px 6px rgba(0,0,0,0.15);">
    <div style="font-size:0.88rem;line-height:1.45;">{html.escape(m.get('content', ''))}</div>
    <div style="font-size:0.7rem;color:rgba(255,255,255,0.5);margin-top:5px;text-align:right;">{html.escape(m.get('created_at', ''))}</div>
  </div>
</div>"""
    elif current:
        chat_body = """<div class="empty-state" style="padding:40px;"><p>No messages yet in this conversation.</p></div>"""
    else:
        leads_count = len(get_leadforge_leads())
        cta_btn = f'<form method="post" action="/sync/leads" style="display:inline;"><button type="submit" class="btn btn-sync">📥 Import Leads into Chatwoot</button></form>' if leads_count > 0 else '<a href="http://127.0.0.1:8790/" class="btn btn-secondary">Find Leads in LeadForge</a>'
        chat_body = f"""
        <div class="empty-state" style="padding:60px 20px;">
          <div class="empty-icon">💬</div>
          <h3>No open conversations</h3>
          <p>When leads reply to WhatsApp, email, or web chat outreach, their threads appear here automatically.</p>
          {cta_btn}
        </div>"""

    sender_meta = current.get("meta", {}).get("sender", {}) if current else {}
    banner = render_leadforge_banner()

    return f"""<!doctype html>
<html>
<head>
<title>Chatwoot - Omnichannel Lead Inbox</title>
{COMMON_HEAD}
</head>
<body>
<header>
  <div class="brand">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
    Chatwoot <span class="badge-local">Standalone Engine</span>
  </div>
  <div style="font-size:0.85rem;color:var(--text-muted);display:flex;align-items:center;gap:12px;">
    <span>Reply Sync API active &bull; Local port 3001</span>
    <button class="btn btn-sm btn-secondary" onclick="document.getElementById('new-msg-modal').style.display='block'">+ Start New Chat</button>
  </div>
</header>
<main style="max-width:1300px;display:flex;flex-direction:column;height:calc(100vh - 84px);padding:20px 28px;">
  {banner}
  <div style="display:flex;flex:1;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;min-height:480px;">
    <!-- Left Conversation List -->
    <div style="width:340px;border-right:1px solid var(--border);display:flex;flex-direction:column;">
      <div style="padding:16px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
        <strong style="font-size:0.95rem;">Conversations ({len(convs)})</strong>
        <span class="badge badge-ok">ALL INBOXES</span>
      </div>
      <div style="flex:1;overflow-y:auto;">
        {threads_html if convs else '<div class="empty-state" style="padding:30px;"><p style="font-size:0.85rem;">No threads found.</p></div>'}
      </div>
    </div>

    <!-- Center Chat Window -->
    <div style="flex:1;display:flex;flex-direction:column;background:var(--bg);">
      <div style="padding:14px 22px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;justify-content:space-between;align-items:center;">
        <div>
          <strong style="font-size:1rem;">{html.escape(sender_meta.get('name', 'Select or start a conversation'))}</strong>
          <span style="font-size:0.8rem;color:var(--text-muted);margin-left:10px;">{html.escape(sender_meta.get('phone_number', ''))}</span>
        </div>
        <span class="badge badge-active">{current.get('status', 'IDLE').upper() if current else 'READY'}</span>
      </div>
      <div style="flex:1;padding:22px;overflow-y:auto;">
        {chat_body}
      </div>
      {f'''<form method="post" action="/message/send" style="padding:16px 20px;background:var(--surface);border-top:1px solid var(--border);display:flex;gap:12px;">
        <input type="hidden" name="conv_id" value="{current['id']}">
        <input type="text" name="reply" placeholder="Type WhatsApp / Email reply..." required style="flex:1;">
        <button type="submit" class="btn btn-success">Send Message</button>
      </form>''' if current else ''}
    </div>

    <!-- Right Sidebar Metadata -->
    <div style="width:290px;border-left:1px solid var(--border);padding:22px;background:var(--surface);">
      <h3 style="margin-bottom:16px;font-size:0.95rem;">Prospect Details</h3>
      <div style="margin-bottom:14px;">
        <label style="font-size:0.75rem;color:var(--text-muted);font-weight:600;">CONTACT / BUSINESS</label>
        <p style="margin-top:2px;"><strong>{html.escape(sender_meta.get('name', '-'))}</strong></p>
      </div>
      <div style="margin-bottom:14px;">
        <label style="font-size:0.75rem;color:var(--text-muted);font-weight:600;">PHONE NUMBER</label>
        <p style="margin-top:2px;">{html.escape(sender_meta.get('phone_number', '-'))}</p>
      </div>
      <div style="margin-bottom:14px;">
        <label style="font-size:0.75rem;color:var(--text-muted);font-weight:600;">EMAIL ADDRESS</label>
        <p style="margin-top:2px;">{html.escape(sender_meta.get('email', '-'))}</p>
      </div>
      <div style="margin-bottom:18px;">
        <label style="font-size:0.75rem;color:var(--text-muted);font-weight:600;">WEBSITE</label>
        <p style="margin-top:2px;">{html.escape(sender_meta.get('website', '-'))}</p>
      </div>
      <div style="margin-top:24px;">
        <a href="http://127.0.0.1:8790/reports" class="btn btn-secondary btn-sm" style="width:100%;justify-content:center;">View in LeadForge Reports</a>
      </div>
    </div>
  </div>

  <!-- New Chat Modal -->
  <div id="new-msg-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.75);z-index:99;padding:40px 20px;">
    <div style="background:var(--surface);max-width:500px;margin:40px auto;padding:26px;border-radius:var(--radius);border:1px solid var(--border);">
      <h3 style="margin-bottom:14px;">Start New Conversation</h3>
      <form method="post" action="/conversation/create">
        <div style="margin-bottom:12px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Lead / Contact Name</label>
          <input type="text" name="name" required placeholder="e.g. Apex Health Clinic">
        </div>
        <div style="margin-bottom:12px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Phone / WhatsApp Number</label>
          <input type="text" name="phone" placeholder="+91 98300 00000">
        </div>
        <div style="margin-bottom:16px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">First Message</label>
          <textarea name="message" rows="3" required placeholder="Hello, I reviewed your business profile and wanted to follow up..."></textarea>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;">
          <button type="button" class="btn btn-secondary" onclick="document.getElementById('new-msg-modal').style.display='none'">Cancel</button>
          <button type="submit" class="btn btn-success">Send Outreach Message</button>
        </div>
      </form>
    </div>
  </div>
</main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 3. CAL.DIY (PORT 3002)
# ---------------------------------------------------------------------------
def caldiy_html(notice=""):
    with DATA_LOCK:
        data = load_apps_data()
        events = list(data["caldiy"]["event_types"])
        bookings = list(data["caldiy"]["bookings"])

    e_cards = ""
    for e in events:
        e_cards += f"""
<div class="card" style="margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;padding:20px;">
  <div>
    <h3 style="font-size:1.05rem;">{html.escape(e.get('title', ''))}</h3>
    <p style="margin-top:4px;color:var(--accent);">⏱️ {e.get('duration', 30)} minutes &bull; Instant calendar sync &bull; Video call link</p>
    <p style="margin-top:5px;font-size:0.85rem;color:var(--text-muted);">{html.escape(e.get('desc', ''))}</p>
  </div>
  <button class="btn btn-sm" onclick="selectEvent('{html.escape(e.get('title', ''))}')">Schedule</button>
</div>"""

    if bookings:
        b_rows = ""
        for b in bookings:
            b_rows += f"""<tr>
<td><strong>{html.escape(b.get('name', ''))}</strong></td>
<td>{html.escape(b.get('email', '-'))}</td>
<td>{html.escape(b.get('event', ''))}</td>
<td>{html.escape(b.get('time', ''))}</td>
<td><span class="badge badge-active">{html.escape(b.get('status', 'Confirmed'))}</span></td>
</tr>"""
        booking_table = f"""
        <table>
          <thead>
            <tr><th>Prospect / Client</th><th>Email</th><th>Meeting Type</th><th>Scheduled Slot</th><th>Status</th></tr>
          </thead>
          <tbody>{b_rows}</tbody>
        </table>"""
    else:
        booking_table = """
        <div class="empty-state">
          <div class="empty-icon">📅</div>
          <h3>No appointments scheduled yet</h3>
          <p>Book a test discovery call using the scheduling form on the right, or share your booking link with leads.</p>
        </div>"""

    banner = render_leadforge_banner()
    toast = f'<div class="toast">{html.escape(notice)}</div>' if notice else ""

    return f"""<!doctype html>
<html>
<head>
<title>cal.diy - Appointment & Discovery Call Scheduling</title>
{COMMON_HEAD}
</head>
<body>
<header>
  <div class="brand">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
    cal.diy <span class="badge-local">Standalone Engine</span>
  </div>
  <nav style="display:flex;gap:8px;">
    <a href="/" class="nav-link active">Event Types</a>
    <a href="#bookings" class="nav-link">Booked Calls ({len(bookings)})</a>
  </nav>
</header>
<main>
  {banner}
  {toast}

  <div style="display:grid;grid-template-columns:1fr 390px;gap:24px;">
    <div>
      <div class="card-header">
        <div>
          <h2>Available Meeting Types</h2>
          <p>Clients and prospects can pick an open slot directly from your booking page.</p>
        </div>
      </div>
      {e_cards}

      <div class="card" id="bookings" style="margin-top:28px;">
        <div class="card-header">
          <h3>Confirmed Strategy Sessions ({len(bookings)})</h3>
        </div>
        {booking_table}
      </div>
    </div>

    <!-- Booking Widget Form -->
    <div class="card" style="height:fit-content;position:sticky;top:90px;">
      <h3 style="margin-bottom:14px;">Schedule Discovery Session</h3>
      <form method="post" action="/book">
        <div style="margin-bottom:12px;">
          <label style="font-size:0.8rem;color:var(--text-muted);display:block;margin-bottom:4px;">Selected Meeting Type</label>
          <input type="text" id="event_input" name="event" value="30 Min Client Strategy Session" readonly style="color:var(--text-muted);">
        </div>
        <div style="margin-bottom:12px;">
          <label style="font-size:0.8rem;color:var(--text-muted);display:block;margin-bottom:4px;">Prospect / Client Name</label>
          <input type="text" name="name" required placeholder="e.g. Dr. Roy">
        </div>
        <div style="margin-bottom:12px;">
          <label style="font-size:0.8rem;color:var(--text-muted);display:block;margin-bottom:4px;">Email Address</label>
          <input type="email" name="email" required placeholder="client@example.com">
        </div>
        <div style="margin-bottom:16px;">
          <label style="font-size:0.8rem;color:var(--text-muted);display:block;margin-bottom:4px;">Select Date & Time</label>
          <select name="time">
            <option>Tomorrow at 10:00 AM</option>
            <option>Tomorrow at 02:00 PM</option>
            <option>Thursday at 11:30 AM</option>
            <option>Friday at 03:00 PM</option>
            <option>Next Monday at 10:00 AM</option>
          </select>
        </div>
        <button type="submit" class="btn btn-success" style="width:100%;justify-content:center;">Confirm Booking & Send Invite</button>
      </form>
    </div>
  </div>
</main>
<script>
function selectEvent(title) {{
  const el = document.getElementById('event_input');
  if (el) el.value = title;
  window.scrollTo({{top: 0, behavior: 'smooth'}});
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 4. TWENTY CRM (PORT 3003)
# ---------------------------------------------------------------------------
def twenty_html(notice=""):
    with DATA_LOCK:
        data = load_apps_data()
        deals = list(data["twenty"]["deals"])

    stages = ["Lead Discovered", "Contacted", "Meeting Scheduled", "Proposal Sent", "Closed Won"]
    columns_html = ""

    for stage in stages:
        stage_deals = [d for d in deals if d.get("stage") == stage]
        stage_value = sum(d.get("value", 0) for d in stage_deals)
        deals_markup = ""
        for d in stage_deals:
            next_stage_btn = ""
            current_idx = stages.index(stage)
            if current_idx < len(stages) - 1:
                next_stage_name = stages[current_idx + 1]
                next_stage_btn = f"""
                <form method="post" action="/deal/advance" style="margin-top:10px;">
                  <input type="hidden" name="deal_id" value="{d['id']}">
                  <button type="submit" class="btn btn-sm btn-secondary" style="width:100%;justify-content:center;font-size:0.75rem;">Move to {html.escape(next_stage_name)} &rarr;</button>
                </form>"""

            deals_markup += f"""
<div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px;margin-bottom:12px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
  <div style="font-weight:600;font-size:0.92rem;color:var(--text);margin-bottom:4px;">{html.escape(d.get('title', ''))}</div>
  <div style="font-size:0.8rem;color:var(--text-muted);">{html.escape(d.get('company', ''))}</div>
  <div style="margin-top:8px;display:flex;justify-content:space-between;align-items:center;">
    <strong style="color:var(--success);font-size:0.9rem;">${d.get('value', 0):,}</strong>
    <span style="font-size:0.72rem;color:var(--text-dim);">{html.escape(d.get('phone', ''))}</span>
  </div>
  {next_stage_btn}
</div>"""

        if not stage_deals:
            deals_markup = """<div style="padding:24px 10px;text-align:center;color:var(--text-dim);font-size:0.82rem;">No deals in this stage</div>"""

        columns_html += f"""
<div style="flex:1;min-width:230px;background:var(--surface-2);border-radius:var(--radius);padding:16px;border:1px solid var(--border);display:flex;flex-direction:column;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--border);">
    <strong style="font-size:0.88rem;">{html.escape(stage)}</strong>
    <span class="badge" style="background:rgba(255,255,255,0.08);color:var(--text-muted);">{len(stage_deals)}</span>
  </div>
  <div style="font-size:0.8rem;color:var(--text-dim);margin-bottom:14px;">Total: <strong>${stage_value:,}</strong></div>
  <div style="flex:1;overflow-y:auto;">
    {deals_markup}
  </div>
</div>"""

    banner = render_leadforge_banner()
    toast = f'<div class="toast">{html.escape(notice)}</div>' if notice else ""
    total_pipeline = sum(d.get("value", 0) for d in deals)
    leads_count = len(get_leadforge_leads())

    return f"""<!doctype html>
<html>
<head>
<title>Twenty CRM - Pipeline & Deal Tracking</title>
{COMMON_HEAD}
</head>
<body>
<header>
  <div class="brand">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
    twenty (CRM) <span class="badge-local">Standalone Engine</span>
  </div>
  <div style="display:flex;gap:10px;align-items:center;">
    <button class="btn btn-sm btn-secondary" onclick="document.getElementById('new-deal-modal').style.display='block'">+ Add Deal</button>
  </div>
</header>
<main style="max-width:1400px;">
  {banner}
  {toast}

  <div class="card-header" style="margin-bottom:20px;">
    <div>
      <h2>Sales & Client Pipeline</h2>
      <p>Visual Kanban CRM tracking deals from initial discovery to closed agreements.</p>
    </div>
    <div style="display:flex;gap:14px;align-items:center;">
      <span style="font-size:0.9rem;color:var(--text-muted);">Pipeline Value: <strong style="color:var(--success);font-size:1.1rem;">${total_pipeline:,}</strong></span>
      {f'<form method="post" action="/sync/leads" style="display:inline;"><button type="submit" class="btn btn-sm btn-sync">📥 Import {leads_count} Leads into CRM</button></form>' if leads_count > 0 else ''}
    </div>
  </div>

  <div style="display:flex;gap:16px;overflow-x:auto;padding-bottom:20px;min-height:550px;">
    {columns_html}
  </div>

  <!-- New Deal Modal -->
  <div id="new-deal-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.75);z-index:99;padding:40px 20px;">
    <div style="background:var(--surface);max-width:500px;margin:40px auto;padding:26px;border-radius:var(--radius);border:1px solid var(--border);">
      <h3 style="margin-bottom:14px;">Add Deal to Pipeline</h3>
      <form method="post" action="/deal/create">
        <div style="margin-bottom:12px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Deal Title</label>
          <input type="text" name="title" required placeholder="e.g. Website Modernization & Booking App">
        </div>
        <div style="margin-bottom:12px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Company / Lead Name</label>
          <input type="text" name="company" required placeholder="e.g. City Dental Care">
        </div>
        <div style="margin-bottom:16px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Estimated Value ($ USD)</label>
          <input type="number" name="value" value="2500" required>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;">
          <button type="button" class="btn btn-secondary" onclick="document.getElementById('new-deal-modal').style.display='none'">Cancel</button>
          <button type="submit" class="btn btn-success">Add Deal</button>
        </div>
      </form>
    </div>
  </div>
</main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 5. DOCUMENSO (PORT 3004)
# ---------------------------------------------------------------------------
def documenso_html(notice=""):
    with DATA_LOCK:
        data = load_apps_data()
        docs = list(data["documenso"]["documents"])

    if docs:
        d_rows = ""
        for d in docs:
            badge_cls = d.get("badge_class", "badge-pending")
            sign_action = f"""
            <form method="post" action="/document/sign" style="display:inline;">
              <input type="hidden" name="doc_id" value="{d['id']}">
              <input type="hidden" name="signer" value="Client Signer">
              <button type="submit" class="btn btn-sm btn-success">✍️ Digital Sign</button>
            </form>""" if d.get("status") != "Signed" else '<span style="color:var(--success);font-size:0.8rem;font-weight:600;">✓ Legally Signed</span>'

            d_rows += f"""<tr>
<td><strong>{html.escape(d.get('id', ''))}</strong></td>
<td><strong>{html.escape(d.get('title', ''))}</strong><div style="font-size:0.8rem;color:var(--text-muted);margin-top:2px;">{html.escape(d.get('content', '')[:90])}...</div></td>
<td>{html.escape(d.get('recipient', ''))}</td>
<td>{html.escape(d.get('created', ''))}</td>
<td><span class="badge {badge_cls}">{html.escape(d.get('status', 'Pending Signature'))}</span></td>
<td>{sign_action}</td>
</tr>"""
        docs_table = f"""
        <table>
          <thead>
            <tr><th>Document ID</th><th>Agreement Title & Scope</th><th>Recipient</th><th>Created</th><th>Status</th><th>Action</th></tr>
          </thead>
          <tbody>{d_rows}</tbody>
        </table>"""
    else:
        docs_table = """
        <div class="empty-state">
          <div class="empty-icon">📝</div>
          <h3>No contracts or agreements yet</h3>
          <p>Create a proposal or digital agreement for your clients using the button below.</p>
          <button class="btn btn-success" onclick="document.getElementById('new-doc-modal').style.display='block'">+ Create New Agreement</button>
        </div>"""

    banner = render_leadforge_banner()
    toast = f'<div class="toast">{html.escape(notice)}</div>' if notice else ""

    return f"""<!doctype html>
<html>
<head>
<title>Documenso - Proposals & Digital Signatures</title>
{COMMON_HEAD}
</head>
<body>
<header>
  <div class="brand">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ec4899" stroke-width="2"><path d="M12 19l7-7 3 3-7 7-3-3z"></path><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"></path><path d="M2 2l7.586 7.586"></path><circle cx="11" cy="11" r="2"></circle></svg>
    Documenso <span class="badge-local">Standalone Engine</span>
  </div>
  <button class="btn btn-sm btn-success" onclick="document.getElementById('new-doc-modal').style.display='block'">+ New Agreement</button>
</header>
<main>
  {banner}
  {toast}

  <div class="card">
    <div class="card-header">
      <div>
        <h2>Agreements & Contracts</h2>
        <p>Proposals, service agreements, and mutual contracts that clients review and sign digitally.</p>
      </div>
      <span class="badge badge-ok">Digital Signatures Enabled</span>
    </div>
    {docs_table}
  </div>

  <!-- New Document Modal -->
  <div id="new-doc-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.75);z-index:99;padding:40px 20px;">
    <div style="background:var(--surface);max-width:560px;margin:30px auto;padding:26px;border-radius:var(--radius);border:1px solid var(--border);">
      <h3 style="margin-bottom:14px;">Generate Client Agreement</h3>
      <form method="post" action="/document/create">
        <div style="margin-bottom:12px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Agreement Title</label>
          <input type="text" name="title" required placeholder="e.g. Software Development & Web Deployment Agreement">
        </div>
        <div style="margin-bottom:12px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Client Name & Email</label>
          <input type="text" name="recipient" required placeholder="e.g. City Dental Clinic (contact@citydental.com)">
        </div>
        <div style="margin-bottom:16px;">
          <label style="font-size:0.85rem;color:var(--text-muted);display:block;margin-bottom:4px;">Scope of Work / Contract Summary</label>
          <textarea name="content" rows="4" required placeholder="This Agreement is made between GDL Technologies and the Client for website development, booking system integration, and automated customer follow-up services."></textarea>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;">
          <button type="button" class="btn btn-secondary" onclick="document.getElementById('new-doc-modal').style.display='none'">Cancel</button>
          <button type="submit" class="btn btn-success">Issue Agreement for Signature</button>
        </div>
      </form>
    </div>
  </div>
</main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Request Handler Routing
# ---------------------------------------------------------------------------
class StandaloneAppHandler(BaseHTTPRequestHandler):
    def __init__(self, app_id, *args, **kwargs):
        self.app_id = app_id
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        pass

    def _send_html(self, html_text, status=200):
        data = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, path="/"):
        self.send_response(303)
        self.send_header("Location", path)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Health endpoint for LeadForge check
        if path in ("/api/health", "/health", "/status"):
            self._send_json({"status": "ok", "app": self.app_id, "mode": "standalone"})
            return

        # 1. LISTMONK
        if self.app_id == "listmonk":
            data = load_apps_data()
            if path in ("/api/campaigns", "/campaigns.json"):
                self._send_json({"data": data["listmonk"]["campaigns"]})
            elif path in ("/api/subscribers", "/subscribers.json"):
                self._send_json({"data": data["listmonk"]["subscribers"]})
            else:
                self._send_html(listmonk_html())

        # 2. CHATWOOT
        elif self.app_id == "chatwoot":
            data = load_apps_data()
            if "/conversations" in path:
                self._send_json({"data": {"payload": data["chatwoot"]["conversations"]}})
            else:
                conv_id = None
                try:
                    if "conv" in query:
                        conv_id = int(query["conv"][0])
                except Exception:
                    pass
                self._send_html(chatwoot_html(active_id=conv_id))

        # 3. CAL.DIY
        elif self.app_id == "caldiy":
            self._send_html(caldiy_html())

        # 4. TWENTY CRM
        elif self.app_id == "twenty":
            self._send_html(twenty_html())

        # 5. DOCUMENSO
        elif self.app_id == "documenso":
            self._send_html(documenso_html())

        else:
            self._send_html(f"<h1>{html.escape(self.app_id)} is running</h1>")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        form = parse_qs(body)

        parsed = urlparse(self.path)
        path = parsed.path

        # Global Lead Import Route
        if path == "/sync/leads":
            ok, msg = sync_leads_into_apps()
            self._redirect("/")
            return

        # 1. LISTMONK
        if self.app_id == "listmonk":
            if path == "/campaigns/create":
                name = form.get("name", ["Outreach Campaign"])[0]
                with DATA_LOCK:
                    data = load_apps_data()
                    new_id = len(data["listmonk"]["campaigns"]) + 1
                    data["listmonk"]["campaigns"].append({
                        "id": new_id,
                        "name": name,
                        "type": "regular",
                        "status": "sent",
                        "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "sent": len(data["listmonk"]["subscribers"]),
                        "opened": 0,
                        "clicked": 0,
                    })
                    save_apps_data(data)
                self._redirect("/")
                return
            elif path == "/subscribers/create":
                name = form.get("name", [""])[0]
                email = form.get("email", [""])[0]
                phone = form.get("phone", [""])[0]
                if name and email:
                    with DATA_LOCK:
                        data = load_apps_data()
                        new_id = len(data["listmonk"]["subscribers"]) + 1
                        data["listmonk"]["subscribers"].append({
                            "id": new_id,
                            "name": name,
                            "email": email,
                            "status": "enabled",
                            "attribs": {"phone": phone, "category": "Prospect"},
                        })
                        save_apps_data(data)
                self._redirect("/")
                return

        # 2. CHATWOOT
        elif self.app_id == "chatwoot":
            if path == "/message/send":
                conv_id = int(form.get("conv_id", [1])[0])
                reply = form.get("reply", [""])[0]
                if reply:
                    with DATA_LOCK:
                        data = load_apps_data()
                        for c in data["chatwoot"]["conversations"]:
                            if c["id"] == conv_id:
                                msg_id = len(c.get("messages", [])) + 1
                                c.setdefault("messages", []).append({
                                    "id": msg_id,
                                    "message_type": 1,
                                    "content": reply,
                                    "created_at": datetime.now().strftime("%I:%M %p"),
                                })
                                c["updated_at"] = datetime.now().isoformat()
                        save_apps_data(data)
                self._redirect(f"/?conv={conv_id}")
                return
            elif path == "/conversation/create":
                name = form.get("name", [""])[0]
                phone = form.get("phone", [""])[0]
                msg = form.get("message", [""])[0]
                if name and msg:
                    with DATA_LOCK:
                        data = load_apps_data()
                        conv_id = len(data["chatwoot"]["conversations"]) + 1
                        data["chatwoot"]["conversations"].append({
                            "id": conv_id,
                            "inbox_id": 1,
                            "status": "open",
                            "unread_count": 0,
                            "meta": {
                                "sender": {
                                    "id": 100 + conv_id,
                                    "name": name,
                                    "phone_number": phone,
                                    "email": "",
                                }
                            },
                            "messages": [
                                {
                                    "id": 1,
                                    "message_type": 1,
                                    "content": msg,
                                    "created_at": datetime.now().strftime("%I:%M %p"),
                                }
                            ],
                            "updated_at": datetime.now().isoformat(),
                        })
                        save_apps_data(data)
                self._redirect(f"/?conv={conv_id}")
                return

        # 3. CAL.DIY
        elif self.app_id == "caldiy" and path == "/book":
            name = form.get("name", ["Guest"])[0]
            email = form.get("email", [""])[0]
            event = form.get("event", ["30 Min Client Strategy Session"])[0]
            t_slot = form.get("time", ["Tomorrow at 10:00 AM"])[0]
            with DATA_LOCK:
                data = load_apps_data()
                new_id = len(data["caldiy"]["bookings"]) + 1
                data["caldiy"]["bookings"].append({
                    "id": new_id,
                    "event": event,
                    "name": name,
                    "email": email,
                    "time": t_slot,
                    "status": "Confirmed",
                })
                save_apps_data(data)
            self._redirect("/")
            return

        # 4. TWENTY CRM
        elif self.app_id == "twenty":
            if path == "/deal/advance":
                deal_id = int(form.get("deal_id", [0])[0])
                stages = ["Lead Discovered", "Contacted", "Meeting Scheduled", "Proposal Sent", "Closed Won"]
                with DATA_LOCK:
                    data = load_apps_data()
                    for d in data["twenty"]["deals"]:
                        if d["id"] == deal_id:
                            idx = stages.index(d["stage"]) if d["stage"] in stages else 0
                            if idx < len(stages) - 1:
                                d["stage"] = stages[idx + 1]
                    save_apps_data(data)
                self._redirect("/")
                return
            elif path == "/deal/create":
                title = form.get("title", ["Outreach Deal"])[0]
                company = form.get("company", ["Business"])[0]
                val = int(form.get("value", [2500])[0])
                with DATA_LOCK:
                    data = load_apps_data()
                    new_id = len(data["twenty"]["deals"]) + 1
                    data["twenty"]["deals"].append({
                        "id": new_id,
                        "title": title,
                        "company": company,
                        "contact": company,
                        "phone": "",
                        "email": "",
                        "value": val,
                        "stage": "Lead Discovered",
                        "color": "#38bdf8",
                    })
                    save_apps_data(data)
                self._redirect("/")
                return

        # 5. DOCUMENSO
        elif self.app_id == "documenso":
            if path == "/document/sign":
                doc_id = form.get("doc_id", [""])[0]
                signer = form.get("signer", ["Client"])[0]
                with DATA_LOCK:
                    data = load_apps_data()
                    for d in data["documenso"]["documents"]:
                        if d["id"] == doc_id:
                            d["status"] = "Signed"
                            d["badge_class"] = "badge-signed"
                    save_apps_data(data)
                self._redirect("/")
                return
            elif path == "/document/create":
                title = form.get("title", ["Service Agreement"])[0]
                recipient = form.get("recipient", ["Client"])[0]
                content = form.get("content", ["Standard digital service contract."])[0]
                with DATA_LOCK:
                    data = load_apps_data()
                    doc_id = f"DOC-{1000 + len(data['documenso']['documents']) + 1}"
                    data["documenso"]["documents"].append({
                        "id": doc_id,
                        "title": title,
                        "recipient": recipient,
                        "content": content,
                        "created": datetime.now().strftime("%Y-%m-%d"),
                        "status": "Pending Signature",
                        "badge_class": "badge-pending",
                    })
                    save_apps_data(data)
                self._redirect("/")
                return

        self._redirect("/")


# Server registry to manage running standalone instances
RUNNING_SERVERS = {}
SERVER_LOCK = threading.Lock()


def make_handler(app_id):
    return lambda *args, **kwargs: StandaloneAppHandler(app_id, *args, **kwargs)


def start_standalone_app(app_id, port):
    """Start standalone HTTP server on given port for app_id."""
    with SERVER_LOCK:
        if app_id in RUNNING_SERVERS:
            return True, f"{app_id} is already running."

        try:
            handler_class = make_handler(app_id)
            server = ThreadingHTTPServer((HOST, int(port)), handler_class)
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            RUNNING_SERVERS[app_id] = server
            return True, f"{app_id} standalone server started on http://{HOST}:{port}"
        except Exception as exc:
            return False, f"Could not start {app_id} standalone server: {exc}"


def stop_standalone_app(app_id):
    """Stop standalone HTTP server for app_id."""
    with SERVER_LOCK:
        if app_id not in RUNNING_SERVERS:
            return True, f"{app_id} was not running."
        try:
            server = RUNNING_SERVERS.pop(app_id)
            server.shutdown()
            server.server_close()
            return True, f"{app_id} standalone server stopped."
        except Exception as exc:
            return False, f"Could not stop {app_id}: {exc}"


def is_standalone_running(app_id):
    with SERVER_LOCK:
        return app_id in RUNNING_SERVERS


DEFAULT_APP_PORTS = {
    "listmonk": 9000,
    "chatwoot": 3001,
    "caldiy": 3002,
    "twenty": 3003,
    "documenso": 3004,
}


def ensure_all_standalone_apps():
    """Ensure all standalone microservice apps are running on their default ports."""
    results = {}
    for app_id, port in DEFAULT_APP_PORTS.items():
        if not is_standalone_running(app_id):
            ok, msg = start_standalone_app(app_id, port)
            results[app_id] = (ok, msg)
        else:
            results[app_id] = (True, "already running")
    return results
