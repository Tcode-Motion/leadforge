"""
LeadForge WhatsApp Web Autonomous Deal Closer Agent
---------------------------------------------------
Uses a persistent Playwright browser context to:
1. Allow 1-time QR scan (stored persistently in dashboard/data/whatsapp_session).
2. Auto-dispatch personalized website conversion audit pitches to verified leads.
3. Listen for incoming replies in real-time.
4. Auto-reply via Gemini / Groq / Local AI / Heuristic deal closure brain.
5. Identify sentiment:
   - Positive/Inquiry -> Send quotation, pitch booking calendar, close deal.
   - Negative/Not interested -> Mark lead as "Not interested" in Leads Store.
   - Meeting scheduled -> Mark lead as "Call booked".
"""

import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# Logging setup
logger = logging.getLogger("whatsapp_agent")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent / "data"
SESSION_DIR = DATA_DIR / "whatsapp_session"
AGENT_STATE_FILE = DATA_DIR / "whatsapp_agent_state.json"
LEADS_STORE_FILE = DATA_DIR / "leads.json"
AGENCY_PROFILE_FILE = DATA_DIR / "agency-profile.json"

STATE = {
    "status": "stopped",       # stopped, qr_needed, ready, running, paused
    "qr_ascii": "",
    "qr_image_url": "",
    "connected_phone": "",
    "active_lead": "",
    "messages_sent": 0,
    "replies_handled": 0,
    "deals_closed": 0,
    "not_interested": 0,
    "current_action": "Agent offline. Click 'Connect WhatsApp Web' to scan QR.",
    "logs": [],
    "last_updated": ""
}

STATE_LOCK = threading.Lock()
AGENT_THREAD = None
STOP_REQUESTED = threading.Event()


def log_event(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    logger.info(entry)
    with STATE_LOCK:
        STATE["logs"].insert(0, entry)
        STATE["logs"] = STATE["logs"][:100]
        STATE["current_action"] = msg
        STATE["last_updated"] = datetime.now().isoformat()
        _save_state()


def get_agent_state():
    with STATE_LOCK:
        return dict(STATE)


def _save_state():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = AGENT_STATE_FILE.with_name(AGENT_STATE_FILE.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(STATE, f, indent=2)
        tmp.replace(AGENT_STATE_FILE)
    except Exception as e:
        logger.error(f"Failed to save whatsapp state: {e}")


def load_leads():
    try:
        if LEADS_STORE_FILE.exists():
            with open(LEADS_STORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return list(data.get("leads", {}).values())
    except Exception as e:
        logger.error(f"Failed to load leads: {e}")
    return []


def update_lead_outcome(lead_name, new_outcome):
    try:
        if not LEADS_STORE_FILE.exists():
            return
        with open(LEADS_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        leads = data.get("leads", {})
        for k, l in leads.items():
            if str(l.get("name", "")).strip().lower() == str(lead_name).strip().lower():
                l["outcome"] = new_outcome
                l["outcome_updated_at"] = datetime.now().isoformat()
                break
        tmp = LEADS_STORE_FILE.with_name(LEADS_STORE_FILE.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(LEADS_STORE_FILE)
        log_event(f"Updated lead '{lead_name}' status to '{new_outcome}' in Leads Store.")
    except Exception as e:
        logger.error(f"Failed to update lead outcome: {e}")


def call_ai_deal_closer(lead_name, prospect_message):
    ai_settings_file = DATA_DIR / "ai-settings.json"
    if not ai_settings_file.exists():
        return None
    try:
        with open(ai_settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        return None

    provider = settings.get("provider", "gemini")
    api_key = settings.get("api_key", "").strip()
    if not api_key and provider != "local":
        return None

    prompt = (
        f"You are Tanmoy, an AI sales strategist at LeadForge Growth Studio closing deals via WhatsApp.\n"
        f"Prospect name / business: {lead_name}\n"
        f"Prospect said: \"{prospect_message}\"\n\n"
        f"Rules:\n"
        f"1. Be friendly, human, and direct. Under 70 words.\n"
        f"2. If they ask about pricing or services, our high-converting mobile booking site is a one-time $199 with zero monthly fees.\n"
        f"3. Provide our discovery call calendar booking link: http://localhost:3002/book/discovery-call\n"
        f"4. Do not invent false guarantees.\n"
        f"Write ONLY the final WhatsApp reply text."
    )

    try:
        import urllib.request
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            req_data = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        elif provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            req_data = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.7
            }).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        elif provider == "local":
            base = settings.get("local_base_url", "http://127.0.0.1:11434").rstrip("/")
            model = settings.get("local_model", "qwen2.5:3b")
            url = f"{base}/v1/chat/completions"
            req_data = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200
            }).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning(f"AI API call failed, falling back to heuristics: {exc}")
    return None


def generate_ai_reply(lead_name, prospect_message, chat_history=""):
    """
    Intelligently analyzes prospect's reply and formulates an expert deal-closing response.
    Classifies intent:
      - 'NOT_INTERESTED'
      - 'BOOKED'
      - 'INQUIRY' / 'POSITIVE'
    """
    msg_lower = prospect_message.lower().strip()

    # Rule-based fast sentiment classification
    negative_signals = [
        "not interested", "stop", "unsubscribe", "don't message", "dont message",
        "remove me", "wrong number", "no thanks", "no thank you", "not needed"
    ]
    if any(sig in msg_lower for sig in negative_signals):
        return {
            "intent": "NOT_INTERESTED",
            "reply": "Understood! Thank you for letting us know, and wishing you all the best with your business.",
            "new_outcome": "Not interested"
        }

    booked_signals = [
        "booked", "scheduled", "see you then", "calendar", "done booking", "picked a slot"
    ]
    if any(sig in msg_lower for sig in booked_signals):
        return {
            "intent": "BOOKED",
            "reply": f"Awesome! Looking forward to our call. We'll have a custom conversion demo ready for {lead_name}.",
            "new_outcome": "Call booked"
        }

    # Try live AI generation if API key is configured
    ai_generated = call_ai_deal_closer(lead_name, prospect_message)
    if ai_generated:
        return {
            "intent": "INQUIRY",
            "reply": ai_generated,
            "new_outcome": "Replied"
        }

    pricing_signals = [
        "how much", "cost", "price", "pricing", "quotation", "quote", "charges", "rate"
    ]
    if any(sig in msg_lower for sig in pricing_signals):
        reply = (
            f"Our high-conversion mobile booking sites start at just $199 one-time with zero recurring fees.\n\n"
            f"It includes:\n"
            f"• 1-page ultra-fast mobile booking site\n"
            f"• Direct 1-click WhatsApp chat button\n"
            f"• 24/7 automated booking calendar\n"
            f"• Full Google Business Profile link setup\n\n"
            f"Would you like to pick a 10-minute slot on our calendar to preview a live mock-up tailored for {lead_name}?\n"
            f"📅 Book here: http://localhost:3002/book/discovery-call"
        )
        return {
            "intent": "INQUIRY",
            "reply": reply,
            "new_outcome": "Replied"
        }

    # Default warm consultative closing response
    reply = (
        f"Thank you for getting back to us! Over 75% of local clients search for services on mobile, "
        f"and businesses with direct WhatsApp and online booking capture most of the inquiries.\n\n"
        f"We can share a quick 2-minute live demo showing how this works for {lead_name}.\n\n"
        f"📅 Pick a convenient time on our calendar whenever you're free:\n"
        f"http://localhost:3002/book/discovery-call\n\n"
        f"Best regards,\nLeadForge Growth Studio"
    )
    return {
        "intent": "INQUIRY",
        "reply": reply,
        "new_outcome": "Replied"
    }


def clean_phone_number(p):
    """Ensure clean international digits e.g. 919836979493."""
    digits = re.sub(r"[^\d]", "", str(p or ""))
    if len(digits) == 10:
        return "91" + digits  # Default India country code if 10 digits
    if digits.startswith("0") and len(digits) == 11:
        return "91" + digits[1:]
    return digits


def is_page_alive(page):
    try:
        return page and not page.is_closed()
    except Exception:
        return False


def run_whatsapp_session():
    """
    Main Playwright driver managing persistent WhatsApp Web context.
    """
    global STOP_REQUESTED
    STOP_REQUESTED.clear()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_event("Playwright is not installed in Python environment.")
        with STATE_LOCK:
            STATE["status"] = "error"
            STATE["current_action"] = "Playwright is not installed. Run 'pip install playwright' once."
            _save_state()
        return

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    log_event(f"Opening WhatsApp Web session at {SESSION_DIR}...")

    context = None
    try:
        with sync_playwright() as p:
            # Launch persistent context without --start-minimized so QR code is clearly visible
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR),
                    headless=False,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 900}
                )
            except Exception as launch_exc:
                logger.warning(f"Chrome channel launch failed ({launch_exc}), falling back to bundled Chromium.")
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR),
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 900}
                )

            page = context.pages[0] if context.pages else context.new_page()
            log_event("Navigating to https://web.whatsapp.com ...")
            try:
                page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=45000)
            except Exception as nav_exc:
                if not is_page_alive(page):
                    log_event("WhatsApp browser window was closed.")
                    return
                log_event(f"Page load note: {nav_exc}")

            # Check authentication status
            with STATE_LOCK:
                STATE["status"] = "connecting"
                STATE["current_action"] = "Checking WhatsApp Web login state..."
                _save_state()

            # Wait for either QR canvas or Main Chats list
            authenticated = False
            start_wait = time.time()
            while time.time() - start_wait < 60 and not STOP_REQUESTED.is_set():
                if not is_page_alive(page):
                    log_event("WhatsApp browser window was closed.")
                    return

                try:
                    if page.locator("#pane-side").count() > 0 or page.locator("div[aria-label='Chat list']").count() > 0:
                        authenticated = True
                        break

                    qr_canvas = page.locator("canvas[aria-label='Scan me!']")
                    if qr_canvas.count() > 0 or page.locator("div[data-ref]").count() > 0:
                        with STATE_LOCK:
                            STATE["status"] = "qr_needed"
                            STATE["current_action"] = "WhatsApp QR code is displayed in the browser window. Please scan with WhatsApp on your phone."
                            _save_state()
                except Exception as check_exc:
                    if "TargetClosedError" in str(type(check_exc)) or not is_page_alive(page):
                        log_event("WhatsApp browser window was closed.")
                        return

                time.sleep(2)

            if not authenticated:
                log_event("Waiting for user to complete WhatsApp QR scan on phone...")
                while not authenticated and not STOP_REQUESTED.is_set():
                    if not is_page_alive(page):
                        log_event("WhatsApp browser window was closed.")
                        return
                    try:
                        if page.locator("#pane-side").count() > 0 or page.locator("div[aria-label='Chat list']").count() > 0:
                            authenticated = True
                            break
                    except Exception as poll_exc:
                        if "TargetClosedError" in str(type(poll_exc)) or not is_page_alive(page):
                            log_event("WhatsApp browser window was closed.")
                            return
                    time.sleep(2)

            if STOP_REQUESTED.is_set() or not is_page_alive(page):
                log_event("WhatsApp agent stopped.")
                return

            log_event("✓ WhatsApp Web authenticated successfully! Session is saved permanently.")
            with STATE_LOCK:
                STATE["status"] = "running"
                STATE["current_action"] = "WhatsApp connected. Starting outreach and listener cycle..."
                _save_state()

            # -------------------------------------------------------------
            # AUTONOMOUS CYCLE: OUTREACH TO NEW LEADS + LISTEN FOR REPLIES
            # -------------------------------------------------------------
            leads = load_leads()
            log_event(f"Loaded {len(leads)} leads from storage.")

            candidates = [
                l for l in leads
                if l.get("phone") and (l.get("outcome", "New") == "New" or not l.get("outcome"))
            ]
            if candidates:
                log_event(f"Found {len(candidates)} new leads ready for automated WhatsApp outreach.")
            else:
                log_event("No pending new leads to pitch. Listening 24/7 for incoming prospect replies.")

            for lead in candidates:
                if STOP_REQUESTED.is_set() or not is_page_alive(page):
                    break

                name = lead.get("name", "Business Owner")
                raw_phone = lead.get("phone", "")
                phone = clean_phone_number(raw_phone)
                website = lead.get("website", "")
                city = lead.get("city") or "your area"

                if not phone or len(phone) < 10:
                    continue

                with STATE_LOCK:
                    STATE["active_lead"] = name
                    STATE["current_action"] = f"Drafting audit pitch for {name} ({phone})..."
                    _save_state()

                if not website:
                    message = (
                        f"Hi {name} Team,\n\n"
                        f"We noticed {name} has a strong presence on Google Maps, but does not have an active website or mobile booking page listed.\n\n"
                        f"Over 75% of local clients search on mobile. Without a mobile booking page, competitors capture these inquiries.\n\n"
                        f"We deploy fast 1-page booking sites with direct 1-click WhatsApp chat for local businesses.\n\n"
                        f"Would you be open to a 2-minute preview showing how this brings 10-15 more clients each month?\n\n"
                        f"📅 Pick a time on our calendar: http://localhost:3002/book/discovery-call\n\n"
                        f"Best regards,\nLeadForge Growth Studio"
                    )
                else:
                    audit = lead.get("audit") or {}
                    recs = audit.get("recommendations") or ["Add an instant WhatsApp floating chat button on mobile"]
                    rec1 = recs[0] if recs else "Add an instant WhatsApp chat button on mobile"
                    message = (
                        f"Hi {name} Team,\n\n"
                        f"We completed a website & conversion audit for {name} ({website}).\n\n"
                        f"We identified a key change to increase client inquiries: {rec1}.\n\n"
                        f"Would you be open to seeing a 2-minute mock-up tailored for your site?\n\n"
                        f"📅 Calendar slot: http://localhost:3002/book/discovery-call\n\n"
                        f"Best regards,\nLeadForge Growth Studio"
                    )

                direct_url = f"https://web.whatsapp.com/send?phone={phone}&text={quote(message)}"
                log_event(f"Opening chat for {name} ({phone})...")
                try:
                    page.goto(direct_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(5)
                except Exception as goto_exc:
                    if not is_page_alive(page):
                        break
                    continue

                try:
                    send_btn = page.locator("button[aria-label='Send'], span[data-icon='send']")
                    if send_btn.count() > 0:
                        send_btn.first.click()
                        log_event(f"✓ Outreach message sent successfully to {name}!")
                        update_lead_outcome(name, "Pitched")
                        with STATE_LOCK:
                            STATE["messages_sent"] += 1
                            _save_state()
                    else:
                        ok_btn = page.locator("div[role='button']:has-text('OK')")
                        if ok_btn.count() > 0:
                            log_event(f"Phone number {phone} for {name} is not on WhatsApp.")
                            ok_btn.first.click()
                            update_lead_outcome(name, "No WhatsApp")
                except Exception as send_err:
                    if not is_page_alive(page):
                        break
                    log_event(f"Outreach notice for {name}: {send_err}")

                # Interval reply check
                wait_end = time.time() + 12
                while time.time() < wait_end and not STOP_REQUESTED.is_set():
                    if not is_page_alive(page):
                        break
                    try:
                        unread_badges = page.locator("span[aria-label*='unread message']")
                        if unread_badges.count() > 0:
                            log_event("⭐ Detected incoming prospect reply! Engaging AI Deal Closer...")
                            unread_badges.first.click()
                            time.sleep(2)
                            messages = page.locator("div.message-in")
                            if messages.count() > 0:
                                last_msg = messages.last.inner_text()
                                chat_header = page.locator("header span[title]").first
                                prospect_name = chat_header.inner_text() if chat_header.count() > 0 else "Prospect"
                                log_event(f"Received reply from {prospect_name}: '{last_msg[:80]}...'")

                                ai_decision = generate_ai_reply(prospect_name, last_msg)
                                log_event(f"AI Decision: Intent={ai_decision['intent']} | Action={ai_decision['new_outcome']}")

                                msg_box = page.locator("div[contenteditable='true'][data-tab='10']")
                                if msg_box.count() > 0:
                                    msg_box.first.click()
                                    msg_box.first.fill(ai_decision["reply"])
                                    time.sleep(1)
                                    page.locator("button[aria-label='Send'], span[data-icon='send']").first.click()
                                    log_event(f"✓ AI response delivered to {prospect_name}!")
                                    update_lead_outcome(prospect_name, ai_decision["new_outcome"])
                                    with STATE_LOCK:
                                        STATE["replies_handled"] += 1
                                        if ai_decision["intent"] in ("BOOKED", "INQUIRY"):
                                            STATE["deals_closed"] += 1
                                        elif ai_decision["intent"] == "NOT_INTERESTED":
                                            STATE["not_interested"] += 1
                                        _save_state()
                    except Exception:
                        if not is_page_alive(page):
                            break
                    time.sleep(2)

            # -------------------------------------------------------------
            # CONTINUOUS LISTENER LOOP (Monitors all incoming replies 24/7)
            # -------------------------------------------------------------
            log_event("Running continuous 24/7 WhatsApp AI Deal Closer listener...")
            with STATE_LOCK:
                STATE["current_action"] = "24/7 WhatsApp AI Deal Closer listening for prospect replies..."
                _save_state()

            while not STOP_REQUESTED.is_set():
                if not is_page_alive(page):
                    log_event("WhatsApp browser window was closed by user.")
                    break

                try:
                    unread_badges = page.locator("span[aria-label*='unread message']")
                    if unread_badges.count() > 0:
                        unread_badges.first.click()
                        time.sleep(2)
                        messages = page.locator("div.message-in")
                        if messages.count() > 0:
                            last_msg = messages.last.inner_text()
                            chat_header = page.locator("header span[title]").first
                            prospect_name = chat_header.inner_text() if chat_header.count() > 0 else "Prospect"
                            log_event(f"Incoming message from {prospect_name}: '{last_msg[:80]}'")

                            ai_decision = generate_ai_reply(prospect_name, last_msg)
                            msg_box = page.locator("div[contenteditable='true'][data-tab='10']")
                            if msg_box.count() > 0:
                                msg_box.first.click()
                                msg_box.first.fill(ai_decision["reply"])
                                time.sleep(1)
                                page.locator("button[aria-label='Send'], span[data-icon='send']").first.click()
                                log_event(f"✓ AI reply sent to {prospect_name}!")
                                update_lead_outcome(prospect_name, ai_decision["new_outcome"])
                                with STATE_LOCK:
                                    STATE["replies_handled"] += 1
                                    if ai_decision["intent"] in ("BOOKED", "INQUIRY"):
                                        STATE["deals_closed"] += 1
                                    elif ai_decision["intent"] == "NOT_INTERESTED":
                                        STATE["not_interested"] += 1
                                    _save_state()
                except Exception as loop_exc:
                    if not is_page_alive(page):
                        log_event("WhatsApp browser window was closed.")
                        break

                time.sleep(3)

    except Exception as exc:
        exc_str = str(exc)
        if "Target page, context or browser has been closed" in exc_str or "TargetClosedError" in exc_str:
            log_event("WhatsApp browser window was closed.")
        else:
            log_event(f"WhatsApp session ended: {exc}")
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        log_event("WhatsApp agent stopped.")
        with STATE_LOCK:
            STATE["status"] = "stopped"
            STATE["current_action"] = "Agent stopped. Click 'Connect WhatsApp Web' to start again."
            _save_state()


def start_whatsapp_agent():
    global AGENT_THREAD
    with STATE_LOCK:
        if STATE["status"] in ("running", "connecting", "qr_needed"):
            return False, "Agent is already active."
        STATE["status"] = "connecting"
        STATE["current_action"] = "Starting WhatsApp Web agent..."
        _save_state()

    AGENT_THREAD = threading.Thread(target=run_whatsapp_session, daemon=True)
    AGENT_THREAD.start()
    return True, "WhatsApp Web Autonomous Agent started."


def stop_whatsapp_agent():
    global STOP_REQUESTED
    STOP_REQUESTED.set()
    with STATE_LOCK:
        STATE["status"] = "stopping"
        STATE["current_action"] = "Stopping WhatsApp Web agent..."
        _save_state()
    return True, "WhatsApp agent stop requested."


if __name__ == "__main__":
    start_whatsapp_agent()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_whatsapp_agent()
