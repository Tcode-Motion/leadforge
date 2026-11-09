"""
LeadForge Deep Intelligence Engine.
Extracts emails, social media profiles (Facebook, Instagram, YouTube, LinkedIn, X/Twitter),
classifies contact numbers (Mobile/WhatsApp Direct vs Business Office Landline),
Google Maps & Business profiles, and performs actionable Website Conversion Audits.
"""

import json
import re
import urllib.parse
from pathlib import Path


def clean_email(email_str):
    if not email_str:
        return ""
    e = str(email_str).strip().lower()
    # Filter false positives
    junk_suffixes = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".css", ".js", ".woff")
    if any(e.endswith(ext) for ext in junk_suffixes):
        return ""
    junk_domains = ("example.com", "domain.com", "yoursite.com", "email.com", "sentry.io", "wixpress.com")
    if any(dom in e for dom in junk_domains):
        return ""
    if e.startswith(("user@", "test@", "rating@", "name@", "yourname@")):
        return ""
    return e


def extract_emails_from_text(text):
    if not text:
        return []
    # Match mailto links first
    mailto_matches = re.findall(r'mailto:([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text, re.I)
    # General email regex
    general_matches = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', text)
    all_candidates = mailto_matches + general_matches
    cleaned = []
    seen = set()
    for cand in all_candidates:
        c = clean_email(cand)
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)
    return cleaned


def classify_phone_number(phone_raw, location=""):
    """
    Classifies phone numbers into 'Mobile / WhatsApp Direct' vs 'Business Office Line'.
    Returns a dict with:
      - cleaned: sanitized number with country code if applicable
      - phone_type: 'Mobile / WhatsApp Direct', 'Business Office Line', or 'Contact Number'
      - is_mobile: boolean
      - is_whatsapp: boolean (whether WhatsApp direct link is viable)
      - whatsapp_url: direct wa.me link if mobile
    """
    if not phone_raw:
        return {
            "cleaned": "",
            "phone_type": "No Phone",
            "is_mobile": False,
            "is_whatsapp": False,
            "whatsapp_url": "",
        }

    raw = str(phone_raw).strip()
    digits = re.sub(r"\D", "", raw)
    loc_lower = str(location or "").lower()

    is_mobile = False
    phone_type = "Business Office Line"
    cleaned = raw

    # India detection (+91 or 10 digits starting with 6, 7, 8, 9)
    is_india = "india" in loc_lower or raw.startswith("+91") or (len(digits) == 10 and digits[0] in "6789")
    if is_india:
        if digits.startswith("91") and len(digits) == 12 and digits[2] in "6789":
            is_mobile = True
            phone_type = "Mobile / WhatsApp Direct"
            cleaned = f"+91 {digits[2:7]} {digits[7:]}"
        elif len(digits) == 10 and digits[0] in "6789":
            is_mobile = True
            phone_type = "Mobile / WhatsApp Direct"
            cleaned = f"+91 {digits[:5]} {digits[5:]}"
            digits = "91" + digits
        elif any(digits.startswith(code) for code in ("011", "022", "033", "080", "044", "020", "079", "040")):
            is_mobile = False
            phone_type = "Business Office Landline"
            cleaned = raw
        else:
            is_mobile = False
            phone_type = "Business Contact Line"

    # UK detection (+44 or 07 mobile vs 01/02 landline)
    elif "uk" in loc_lower or raw.startswith("+44") or digits.startswith("44") or (digits.startswith("07") and len(digits) == 11):
        if (digits.startswith("447") and len(digits) == 12) or (digits.startswith("07") and len(digits) == 11):
            is_mobile = True
            phone_type = "Mobile / WhatsApp Direct"
        elif any(digits.startswith(p) for p in ("01", "02", "441", "442")):
            is_mobile = False
            phone_type = "Business Office Landline"
        else:
            phone_type = "Business Line"

    # US / Canada detection (+1 or 10 digits)
    elif "usa" in loc_lower or "us" in loc_lower or "canada" in loc_lower or raw.startswith("+1") or len(digits) == 10:
        ten_digits = digits[-10:] if len(digits) >= 10 else digits
        area_code = ten_digits[:3] if len(ten_digits) >= 3 else ""
        if area_code in ("800", "888", "877", "866", "855", "844", "833"):
            is_mobile = False
            phone_type = "Toll-Free Business Line"
        else:
            # US cell/mobile vs landline is mixed, default to Direct Business Line
            phone_type = "Direct Business Line"
            if len(ten_digits) == 10:
                is_mobile = True  # SMS and WhatsApp capable
    else:
        # Generic international
        if len(digits) >= 10:
            is_mobile = True
            phone_type = "Direct Mobile / WhatsApp"
        else:
            phone_type = "Business Contact Line"

    # WhatsApp link
    whatsapp_url = ""
    if is_mobile and len(digits) >= 10:
        whatsapp_url = f"https://wa.me/{digits}"

    return {
        "cleaned": cleaned,
        "phone_type": phone_type,
        "is_mobile": is_mobile,
        "is_whatsapp": bool(whatsapp_url),
        "whatsapp_url": whatsapp_url,
    }


def extract_social_links(text, business_name="", city=""):
    """
    Extracts Facebook, Instagram, YouTube, LinkedIn, and Twitter/X URLs.
    If not explicitly present, generates high-intent profile search links.
    """
    t = str(text or "")
    social = {
        "facebook": "",
        "instagram": "",
        "youtube": "",
        "linkedin": "",
        "twitter": "",
    }

    # Facebook
    fb_m = re.search(r'https?://(?:www\.)?(?:facebook\.com|fb\.com)/(?!sharer|share|plugins|policies|login|dialog)([A-Za-z0-9._-]+)', t, re.I)
    if fb_m:
        social["facebook"] = f"https://www.facebook.com/{fb_m.group(1)}"

    # Instagram
    ig_m = re.search(r'https?://(?:www\.)?instagram\.com/(?!p/|reel/|explore/|stories/|developer/)([A-Za-z0-9._-]+)', t, re.I)
    if ig_m:
        social["instagram"] = f"https://www.instagram.com/{ig_m.group(1)}"

    # YouTube
    yt_m = re.search(r'https?://(?:www\.)?youtube\.com/(?!watch|playlist|embed|feed)(@[A-Za-z0-9._-]+|channel/[A-Za-z0-9_-]+|c/[A-Za-z0-9._-]+)', t, re.I)
    if yt_m:
        social["youtube"] = f"https://www.youtube.com/{yt_m.group(1)}"

    # LinkedIn
    li_m = re.search(r'https?://(?:www\.)?linkedin\.com/(company/[A-Za-z0-9._-]+|in/[A-Za-z0-9._-]+)', t, re.I)
    if li_m:
        social["linkedin"] = f"https://www.linkedin.com/{li_m.group(1)}"

    # Twitter / X
    tw_m = re.search(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/(?!intent|share|privacy)([A-Za-z0-9_]+)', t, re.I)
    if tw_m:
        social["twitter"] = f"https://x.com/{tw_m.group(1)}"

    # Only return exact verified social profile URLs - never generate fake Google searches
    return {
        "links": social,
        "search_fallbacks": {},
        "has_facebook": bool(social["facebook"]),
        "has_instagram": bool(social["instagram"]),
        "has_youtube": bool(social["youtube"]),
        "has_linkedin": bool(social["linkedin"]),
        "has_twitter": bool(social["twitter"]),
    }


def audit_website(url, html_or_text=""):
    """
    Performs a conversion and technical audit on a lead's website.
    Returns:
      - score: integer 0-100
      - has_ssl: boolean
      - has_viewport: boolean
      - has_whatsapp: boolean
      - has_booking: boolean
      - has_click_to_call: boolean
      - has_reviews: boolean
      - missing_critical: list of strings
      - recommendations: list of actionable improvement sentences
    """
    if not url:
        return {
            "has_website": False,
            "score": 0,
            "badge": "No Website (Prime Pitch)",
            "summary": "This business has zero web presence. They lose 100% of organic search traffic to local competitors.",
            "recommendations": [
                "Pitch a modern mobile-first booking website with WhatsApp integration.",
                "Set up Google Business profile website link to capture local searchers.",
                "Deploy an automated 1-click scheduling calendar (Cal.diy).",
            ],
            "pitch_angle": "no_website",
        }

    raw = str(html_or_text or "")
    raw_lower = raw.lower()

    # 1. SSL Check
    has_ssl = url.startswith("https://")

    # 2. Mobile Responsive (Viewport)
    has_viewport = bool(re.search(r'<meta[^>]+name=["\']viewport["\']', raw, re.I) or "viewport" in raw_lower)

    # 3. WhatsApp Direct Chat Button
    has_whatsapp = bool(
        "wa.me/" in raw_lower
        or "api.whatsapp.com" in raw_lower
        or "whatsapp" in raw_lower and ("chat" in raw_lower or "send" in raw_lower)
    )

    # 4. Online Booking / Scheduling Calendar
    has_booking = bool(
        any(k in raw_lower for k in ("calendly.com", "cal.com", "practo.com", "zocdoc.com", "acuityscheduling.com"))
        or ("book" in raw_lower and ("appointment" in raw_lower or "online" in raw_lower or "schedule" in raw_lower))
    )

    # 5. Click to Call (tel:)
    has_click_to_call = bool("href=\"tel:" in raw_lower or "href='tel:" in raw_lower or "tel:" in raw_lower)

    # 6. Social Proof / Google Reviews Widget
    has_reviews = bool(
        any(k in raw_lower for k in ("review", "testimonial", "google rating", "patient reviews", "stars", "feedback"))
    )

    # Calculate Score
    score = 40  # base for having a site
    if has_ssl:
        score += 15
    if has_viewport:
        score += 15
    if has_click_to_call:
        score += 10
    if has_whatsapp:
        score += 10
    if has_booking:
        score += 10

    # Build recommendations
    missing_critical = []
    recommendations = []

    if not has_ssl:
        missing_critical.append("Insecure HTTP connection")
        recommendations.append("Upgrade site to HTTPS / SSL encryption to stop browsers from showing scary 'Not Secure' warnings to prospective clients.")

    if not has_whatsapp:
        missing_critical.append("No instant WhatsApp chat button")
        recommendations.append("Add a floating 1-click WhatsApp chat button on mobile (over 65% of mobile searchers prefer asking questions on WhatsApp before calling).")

    if not has_booking:
        missing_critical.append("No 24/7 online booking calendar")
        recommendations.append("Add automated self-scheduling (Cal.com / Cal.diy) so clients browsing in the evening can book appointments after your front desk closes.")

    if not has_click_to_call:
        missing_critical.append("No sticky click-to-call button")
        recommendations.append("Add a sticky click-to-call phone button in the mobile header so smartphone visitors can tap and dial instantly.")

    if not has_reviews:
        missing_critical.append("Missing live Google reviews widget")
        recommendations.append("Embed an automated Google Reviews & star rating badge on the homepage to instantly build trust with new visitors.")

    if not recommendations:
        recommendations.append("Website fundamentals are good. Pitch automated WhatsApp follow-up reminders and Google review booster campaigns.")

    return {
        "has_website": True,
        "score": min(100, score),
        "has_ssl": has_ssl,
        "has_viewport": has_viewport,
        "has_whatsapp": has_whatsapp,
        "has_booking": has_booking,
        "has_click_to_call": has_click_to_call,
        "has_reviews": has_reviews,
        "missing_critical": missing_critical,
        "recommendations": recommendations,
        "pitch_angle": "conversion_upgrade" if missing_critical else "growth_automation",
    }


def analyze_lead_intelligence(lead, note_text=""):
    """
    Comprehensive analyzer for a lead record.
    Aggregates emails, contact classification, social links, Google Maps links,
    and website conversion audit.
    """
    name = str(lead.get("name") or lead.get("title") or "Business").strip()
    address = str(lead.get("address") or lead.get("complete_address") or "").strip()
    city = str(lead.get("city") or "")
    if not city and address:
        parts = [p.strip() for p in address.split(",")]
        if len(parts) >= 3:
            city = parts[-3]
        elif len(parts) >= 2:
            city = parts[-2]

    website = str(lead.get("website") or lead.get("url") or "").strip()
    phone_raw = str(lead.get("phone") or "").strip()

    # 1. Emails
    existing_emails = str(lead.get("emails") or lead.get("email") or "").strip()
    emails = []
    if existing_emails:
        emails.extend([clean_email(e) for e in re.split(r"[,;\s]+", existing_emails) if clean_email(e)])
    if note_text:
        emails.extend(extract_emails_from_text(note_text))
    # Deduplicate
    emails = list(dict.fromkeys([e for e in emails if e]))
    primary_email = emails[0] if emails else ""
    if not primary_email and website:
        # Domain suggestion
        dom = website.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
        if dom and "." in dom:
            primary_email = f"contact@{dom}"

    # 2. Phone Classification
    phone_info = classify_phone_number(phone_raw, location=address or city)

    # 3. Social Media Links
    social_info = extract_social_links(note_text, business_name=name, city=city)

    # 4. Google Maps & Place Links
    maps_link = str(lead.get("link") or "").strip()
    if not maps_link or not ("maps.google" in maps_link or "google.com/maps" in maps_link):
        q = urllib.parse.quote(f"{name} {address}".strip())
        maps_link = f"https://www.google.com/maps/search/?api=1&query={q}"

    review_search_link = f"https://www.google.com/search?q={urllib.parse.quote(name + ' ' + (city or address) + ' reviews')}"

    # 5. Website Conversion Audit
    audit_info = audit_website(website, html_or_text=note_text)

    return {
        "name": name,
        "address": address,
        "city": city,
        "website": website,
        "phone": phone_info["cleaned"] or phone_raw,
        "phone_type": phone_info["phone_type"],
        "is_mobile": phone_info["is_mobile"],
        "is_whatsapp": phone_info["is_whatsapp"],
        "whatsapp_url": phone_info["whatsapp_url"],
        "emails": emails,
        "primary_email": primary_email,
        "email_is_suggested": bool(not emails and primary_email),
        "social": social_info["links"],
        "social_search": {},
        "maps_url": maps_link,
        "reviews_search_url": review_search_link,
        "audit": audit_info,
    }

