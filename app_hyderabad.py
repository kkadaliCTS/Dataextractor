import json
import re
import csv
import time
import threading
import webbrowser
from io import StringIO
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template_string, request, jsonify, make_response
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
extracted_businesses = []

# ============================================================
#  CONFIG
# ============================================================
HYDERABAD_LAT = 17.3850
HYDERABAD_LNG = 78.4867
SEARCH_RADIUS = 15000

CATEGORIES = {
    "it_companies":    {"keyword": "IT companies",           "type": "establishment"},
    "software":        {"keyword": "software company",       "type": "establishment"},
    "startups":        {"keyword": "startup",                "type": "establishment"},
    "restaurants":     {"keyword": "restaurant",             "type": "restaurant"},
    "hospitals":       {"keyword": "hospital",               "type": "hospital"},
    "hotels":          {"keyword": "hotel",                  "type": "lodging"},
    "real_estate":     {"keyword": "real estate agency",     "type": "real_estate_agency"},
    "gyms":            {"keyword": "gym fitness",            "type": "gym"},
    "education":       {"keyword": "coaching institute",     "type": "establishment"},
    "retail_shops":    {"keyword": "retail shop",            "type": "store"},
    "manufacturers":   {"keyword": "manufacturer factory",   "type": "establishment"},
    "pharma":          {"keyword": "pharmaceutical company", "type": "establishment"},
    "marketing":       {"keyword": "marketing agency",       "type": "establishment"},
    "logistics":       {"keyword": "logistics courier",      "type": "establishment"},
    "automobile":      {"keyword": "car dealer showroom",    "type": "car_dealer"},
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
MAILTO_RE = re.compile(r"mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", re.IGNORECASE)

JUNK_EMAILS = {
    "sentry@", "wixpress", "example.com", "domain.com",
    "email@", "username@", "test@", "noreply@", "no-reply@",
    ".png", ".jpg", ".gif", ".svg", ".webp", "google.com",
    "gstatic", "w3.org", "schema.org", "facebook.com",
    "twitter.com", "instagram.com", "youtube.com",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

ai_api_key = ""


def is_junk_email(email):
    e = email.lower()
    return any(j in e for j in JUNK_EMAILS)


# ============================================================
#  AI LAYER — Claude API for intelligent extraction
# ============================================================
def ai_extract_contact_info(company_name, webpage_text, website_url):
    global ai_api_key
    if not ai_api_key or not webpage_text:
        return {}
    text_chunk = webpage_text[:4000]
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ai_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Extract business contact information from this webpage text for the company "{company_name}" (website: {website_url}).

Return ONLY a JSON object with these fields (use null if not found):
{{
  "emails": ["list of email addresses found"],
  "phones": ["list of phone numbers found"],
  "contact_person": "name of contact person if found",
  "business_description": "one line description of what this business does",
  "services": "main services offered",
  "social_media": {{"linkedin": "url", "twitter": "url", "facebook": "url"}}
}}

Webpage text:
{text_chunk}

Return ONLY the JSON, no other text."""
                    }
                ],
            },
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            ai_text = data.get("content", [{}])[0].get("text", "")
            ai_text = ai_text.strip()
            if ai_text.startswith("```"):
                ai_text = ai_text.split("\n", 1)[-1].rsplit("```", 1)[0]
            return json.loads(ai_text)
    except Exception as e:
        print(f"  [AI] Extract error: {e}")
    return {}


def ai_validate_and_score_email(email, company_name, domain):
    global ai_api_key
    if not ai_api_key or not email:
        return {"valid": True, "confidence": "medium"}
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ai_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Is this email likely a real business contact email?
Email: {email}
Company: {company_name}
Website domain: {domain}

Return ONLY JSON: {{"valid": true/false, "confidence": "high"/"medium"/"low", "reason": "brief reason"}}"""
                    }
                ],
            },
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            ai_text = data.get("content", [{}])[0].get("text", "").strip()
            if ai_text.startswith("```"):
                ai_text = ai_text.split("\n", 1)[-1].rsplit("```", 1)[0]
            return json.loads(ai_text)
    except Exception:
        pass
    return {"valid": True, "confidence": "medium"}


def ai_generate_business_summary(company_name, address, website, rating, reviews):
    global ai_api_key
    if not ai_api_key:
        return "N/A"
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ai_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 80,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Write a one-line business description (max 15 words) for:
Company: {company_name}
Address: {address}
Website: {website}
Rating: {rating}/5 ({reviews} reviews)

Return ONLY the description, no quotes or extra text."""
                    }
                ],
            },
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("content", [{}])[0].get("text", "N/A").strip()
    except Exception:
        pass
    return "N/A"


# ============================================================
#  EMAIL FINDING — 4 LAYERS
# ============================================================

def scrape_emails_from_website(website_url, timeout=8):
    if not website_url:
        return [], ""
    try:
        emails = set()
        all_text = ""

        try:
            resp = requests.get(website_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            page_text = resp.text
            emails |= {e for e in EMAIL_RE.findall(page_text) if not is_junk_email(e)}
            emails |= {e for e in MAILTO_RE.findall(page_text) if not is_junk_email(e)}

            soup = BeautifulSoup(page_text, "html.parser")
            all_text = soup.get_text(separator=" ", strip=True)

            contact_keywords = ["contact", "about", "reach", "connect", "support",
                                "help", "team", "info", "enquiry", "inquiry",
                                "feedback", "get-in-touch"]
            internal_links = set()
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].lower()
                if any(kw in href for kw in contact_keywords):
                    full_url = href
                    if href.startswith("/"):
                        full_url = website_url.rstrip("/") + href
                    elif not href.startswith("http"):
                        full_url = website_url.rstrip("/") + "/" + href
                    internal_links.add(full_url)
        except Exception:
            internal_links = set()

        common_pages = [
            "/contact", "/contact-us", "/contactus",
            "/about", "/about-us", "/aboutus",
            "/support", "/help", "/reach-us",
            "/get-in-touch", "/connect", "/enquiry",
        ]
        for suffix in common_pages:
            internal_links.add(website_url.rstrip("/") + suffix)

        for link in list(internal_links)[:10]:
            try:
                sub = requests.get(link, headers=HEADERS, timeout=6, allow_redirects=True)
                if sub.status_code == 200:
                    emails |= {e for e in EMAIL_RE.findall(sub.text) if not is_junk_email(e)}
                    emails |= {e for e in MAILTO_RE.findall(sub.text) if not is_junk_email(e)}
                    soup2 = BeautifulSoup(sub.text, "html.parser")
                    all_text += " " + soup2.get_text(separator=" ", strip=True)
            except Exception:
                continue

        return list(emails)[:5], all_text[:5000]
    except Exception:
        return [], ""


def google_search_email(company_name):
    try:
        query = f"{company_name} Hyderabad email address contact"
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            emails = EMAIL_RE.findall(resp.text)
            emails = [e for e in emails if not is_junk_email(e)]
            return emails[:2]
    except Exception:
        pass
    return []


def generate_common_emails(company_name, website):
    if not website or website == "N/A":
        return []
    try:
        domain = urlparse(website).netloc
        if domain.startswith("www."):
            domain = domain[4:]
        if not domain:
            return []
        skip_domains = ["google", "facebook", "instagram", "youtube", "twitter", "linkedin", "justdial", "indiamart"]
        if any(sd in domain.lower() for sd in skip_domains):
            return []
        return [f"info@{domain}"]
    except Exception:
        return []


# ============================================================
#  GOOGLE PLACES APIs
# ============================================================
def google_nearby_search(api_key, keyword, place_type, max_pages=3):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{HYDERABAD_LAT},{HYDERABAD_LNG}",
        "radius": SEARCH_RADIUS,
        "keyword": keyword,
        "type": place_type,
        "key": api_key,
    }
    all_results = []
    for _ in range(max_pages):
        resp = requests.get(url, params=params, timeout=15).json()
        if resp.get("status") not in ("OK", "ZERO_RESULTS"):
            break
        all_results.extend(resp.get("results", []))
        token = resp.get("next_page_token")
        if not token:
            break
        time.sleep(2)
        params = {"pagetoken": token, "key": api_key}
    return all_results


def google_place_details(api_key, place_id):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "formatted_phone_number,international_phone_number,website,formatted_address,url,business_status",
        "key": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=10).json()
        if resp.get("status") == "OK":
            return resp.get("result", {})
    except Exception:
        pass
    return {}


# ============================================================
#  ENRICHMENT — 4-layer email + AI extraction
# ============================================================
def enrich_place(api_key, place):
    global ai_api_key
    place_id = place.get("place_id", "")
    details = google_place_details(api_key, place_id) if place_id else {}

    phone = (
        details.get("formatted_phone_number")
        or details.get("international_phone_number")
        or "N/A"
    )
    website = details.get("website", "")
    full_address = details.get("formatted_address") or place.get("vicinity", "N/A")
    maps_url = details.get("url", "")
    biz_status = details.get("business_status", "N/A")
    company_name = place.get("name", "N/A")

    emails = []
    email_type = "N/A"
    ai_description = "N/A"
    ai_services = "N/A"
    contact_person = "N/A"
    email_confidence = "N/A"

    # Layer 1: Deep website scraping
    scraped_emails, webpage_text = scrape_emails_from_website(website)
    if scraped_emails:
        emails.extend(scraped_emails)
        email_type = "verified"

    # Layer 2: Google search
    if not emails:
        searched = google_search_email(company_name)
        if searched:
            emails.extend(searched)
            email_type = "verified"

    # Layer 3: AI-powered extraction
    if ai_api_key and webpage_text:
        ai_data = ai_extract_contact_info(company_name, webpage_text, website)
        if ai_data:
            ai_emails = ai_data.get("emails") or []
            ai_emails = [e for e in ai_emails if e and not is_junk_email(e)]
            if ai_emails and not emails:
                emails.extend(ai_emails)
                email_type = "ai_extracted"
            elif ai_emails:
                for ae in ai_emails:
                    if ae not in emails:
                        emails.append(ae)

            ai_phones = ai_data.get("phones") or []
            if ai_phones and phone == "N/A":
                phone = ai_phones[0]

            contact_person = ai_data.get("contact_person") or "N/A"
            ai_description = ai_data.get("business_description") or "N/A"
            ai_services = ai_data.get("services") or "N/A"

    # Layer 4: Smart guessing
    if not emails:
        guessed = generate_common_emails(company_name, website)
        if guessed:
            emails.extend(guessed)
            email_type = "guessed"

    # AI email validation
    if emails and ai_api_key and email_type in ("verified", "ai_extracted"):
        domain = urlparse(website).netloc if website else ""
        validation = ai_validate_and_score_email(emails[0], company_name, domain)
        email_confidence = validation.get("confidence", "medium")
    elif email_type == "guessed":
        email_confidence = "low"
    elif emails:
        email_confidence = "medium"

    # AI business summary
    if ai_api_key and ai_description == "N/A":
        ai_description = ai_generate_business_summary(
            company_name, full_address, website,
            place.get("rating", "N/A"), place.get("user_ratings_total", 0)
        )

    emails = list(dict.fromkeys(emails))[:3]
    email_str = ", ".join(emails) if emails else "N/A"

    return {
        "company": company_name,
        "address": full_address,
        "phone": phone,
        "email": email_str,
        "email_type": email_type,
        "email_confidence": email_confidence,
        "contact_person": contact_person,
        "website": website or "N/A",
        "rating": place.get("rating", "N/A"),
        "reviews": place.get("user_ratings_total", 0),
        "status": biz_status,
        "description": ai_description,
        "services": ai_services,
        "maps_link": maps_url,
    }


# ============================================================
#  HTML TEMPLATE
# ============================================================
CATS_JSON = json.dumps({k: {"keyword": v["keyword"]} for k, v in CATEGORIES.items()})

HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>AI Business Data Extractor</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);min-height:100vh;color:#e0e0e0}
.header{text-align:center;padding:40px 20px 20px}
.header h1{font-size:36px;background:linear-gradient(135deg,#667eea,#764ba2,#f093fb);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}
.header p{color:#aaa;font-size:15px}
.ai-badge{display:inline-block;padding:4px 14px;border-radius:20px;font-size:12px;font-weight:700;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;margin-top:8px}
.main{max-width:1300px;margin:0 auto;padding:20px}
.card{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:30px;margin-bottom:24px;backdrop-filter:blur(10px)}
.card h2{font-size:20px;margin-bottom:18px;color:#c9b1ff}
.form-row{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.form-group{flex:1;min-width:200px}
.form-group label{display:block;font-size:13px;font-weight:600;color:#bbb;margin-bottom:6px}
.form-group input,.form-group select{width:100%;padding:12px;border:1px solid rgba(255,255,255,0.15);border-radius:10px;background:rgba(255,255,255,0.07);color:#fff;font-size:14px;outline:none;transition:.3s}
.form-group input:focus,.form-group select:focus{border-color:#667eea;background:rgba(255,255,255,0.12)}
select option{background:#302b63;color:#fff}
.btn{padding:14px 32px;border:none;border-radius:10px;font-weight:700;font-size:15px;cursor:pointer;transition:.3s}
.btn-primary{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(102,126,234,.4)}
.btn-primary:disabled{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none}
.btn-success{background:linear-gradient(135deg,#11998e,#38ef7d);color:#000;font-weight:700}
.btn-success:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(56,239,125,.3)}
.btn-row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:8px}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin-top:20px}
.stat-box{flex:1;min-width:110px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:14px;text-align:center}
.stat-box .num{font-size:24px;font-weight:800;background:linear-gradient(135deg,#667eea,#f093fb);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-box .lbl{font-size:10px;color:#999;margin-top:4px}
.msg{margin-top:16px;padding:14px;border-radius:10px;font-size:14px;display:none}
.msg.show{display:block}
.msg.error{background:rgba(220,53,69,.15);color:#ff6b6b;border:1px solid rgba(220,53,69,.25)}
.msg.success{background:rgba(56,239,125,.1);color:#38ef7d;border:1px solid rgba(56,239,125,.2)}
.msg.loading{background:rgba(102,126,234,.1);color:#a5b4fc;border:1px solid rgba(102,126,234,.2)}
.table-wrap{overflow-x:auto;margin-top:16px;border-radius:12px;border:1px solid rgba(255,255,255,.08)}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:rgba(102,126,234,.25);color:#c9b1ff;padding:10px 8px;text-align:left;white-space:nowrap;font-weight:700;position:sticky;top:0}
td{padding:8px;border-bottom:1px solid rgba(255,255,255,.06);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr:hover td{background:rgba(255,255,255,.04)}
a{color:#667eea;text-decoration:none}
a:hover{text-decoration:underline}
.checkbox-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;margin-top:8px}
.checkbox-grid label{display:flex;align-items:center;gap:6px;font-size:13px;color:#ccc;cursor:pointer;padding:6px 10px;border-radius:8px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);transition:.2s}
.checkbox-grid label:hover{background:rgba(102,126,234,.12);border-color:rgba(102,126,234,.3)}
.checkbox-grid input[type=checkbox]{accent-color:#667eea}
.help-text{font-size:12px;color:#888;margin-top:6px}
.footer{text-align:center;padding:30px;color:#555;font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:700}
.badge-verified{background:rgba(56,239,125,.15);color:#38ef7d}
.badge-ai{background:rgba(102,126,234,.2);color:#a5b4fc}
.badge-guessed{background:rgba(255,193,7,.15);color:#ffc107}
.badge-high{background:rgba(56,239,125,.15);color:#38ef7d}
.badge-medium{background:rgba(255,193,7,.15);color:#ffc107}
.badge-low{background:rgba(220,53,69,.15);color:#ff6b6b}
.optional-tag{font-size:10px;color:#888;background:rgba(255,255,255,.06);padding:2px 6px;border-radius:4px;margin-left:4px}
</style>
</head>
<body>

<div class="header">
    <h1>AI Business Data Extractor</h1>
    <p>Intelligent data extraction with <strong>AI-powered</strong> email finding, validation and business insights</p>
    <div class="ai-badge">Powered by Claude AI + Google Maps</div>
</div>

<div class="main">
    <div class="card">
        <h2>Configuration</h2>
        <div class="form-row">
            <div class="form-group">
                <label>Google Places API Key *</label>
                <input type="password" id="apiKey" placeholder="Required — for business search" autocomplete="off">
                <div class="help-text"><a href="https://console.cloud.google.com" target="_blank">Get key</a> — Free $200/month</div>
            </div>
            <div class="form-group">
                <label>Claude AI API Key <span class="optional-tag">Optional</span></label>
                <input type="password" id="aiKey" placeholder="Optional — enables AI features" autocomplete="off">
                <div class="help-text"><a href="https://console.anthropic.com" target="_blank">Get key</a> — Enables smart extraction</div>
            </div>
            <div class="form-group">
                <label>Max Pages</label>
                <select id="maxPages">
                    <option value="1">1 page (~20)</option>
                    <option value="2" selected>2 pages (~40)</option>
                    <option value="3">3 pages (~60)</option>
                </select>
            </div>
        </div>

        <label style="font-size:14px;font-weight:700;color:#c9b1ff;margin-bottom:4px;display:block">Select Business Categories</label>
        <div class="checkbox-grid" id="catGrid"></div>
        <div class="help-text" style="margin-top:8px">More categories = more businesses.</div>

        <div class="btn-row">
            <button class="btn btn-primary" id="extractBtn" onclick="startExtraction()">Extract Businesses</button>
            <button class="btn btn-success" id="downloadBtn" onclick="location.href='/download'" style="display:none">Download CSV</button>
        </div>

        <div class="msg" id="msg"></div>

        <div class="stats" id="stats" style="display:none">
            <div class="stat-box"><div class="num" id="sTotalBiz">0</div><div class="lbl">Businesses</div></div>
            <div class="stat-box"><div class="num" id="sPhones">0</div><div class="lbl">Phones</div></div>
            <div class="stat-box"><div class="num" id="sVerified">0</div><div class="lbl">Verified Emails</div></div>
            <div class="stat-box"><div class="num" id="sAiEmails">0</div><div class="lbl">AI Extracted</div></div>
            <div class="stat-box"><div class="num" id="sGuessed">0</div><div class="lbl">Guessed</div></div>
            <div class="stat-box"><div class="num" id="sWebsites">0</div><div class="lbl">Websites</div></div>
        </div>
    </div>

    <div class="card" id="resultsCard" style="display:none">
        <h2>Extracted Businesses</h2>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>#</th><th>Company</th><th>Phone</th><th>Email</th>
                        <th>Source</th><th>Confidence</th><th>Contact Person</th>
                        <th>Description</th><th>Website</th><th>Rating</th><th>Reviews</th>
                    </tr>
                </thead>
                <tbody id="resultsBody"></tbody>
            </table>
        </div>
    </div>
</div>

<div class="footer">AI Business Data Extractor — Google Places API + Claude AI + Web Scraping</div>

<script>
var cats = CATEGORIES_PLACEHOLDER;
var grid = document.getElementById('catGrid');
Object.entries(cats).forEach(function(entry) {
    var key = entry[0], val = entry[1];
    var lbl = document.createElement('label');
    var chk = ['it_companies','software','startups'].indexOf(key) >= 0 ? 'checked' : '';
    lbl.innerHTML = '<input type="checkbox" name="cat" value="' + key + '" ' + chk + '> ' + val.keyword;
    grid.appendChild(lbl);
});

function showMsg(text, type) {
    var m = document.getElementById('msg');
    m.className = 'msg show ' + type;
    m.innerHTML = text;
}

function esc(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
}

function badgeFor(type) {
    if (type === 'verified') return '<span class="badge badge-verified">Verified</span>';
    if (type === 'ai_extracted') return '<span class="badge badge-ai">AI Found</span>';
    if (type === 'guessed') return '<span class="badge badge-guessed">Guessed</span>';
    return '-';
}

function confBadge(c) {
    if (c === 'high') return '<span class="badge badge-high">High</span>';
    if (c === 'medium') return '<span class="badge badge-medium">Medium</span>';
    if (c === 'low') return '<span class="badge badge-low">Low</span>';
    return '-';
}

function startExtraction() {
    var apiKey = document.getElementById('apiKey').value.trim();
    if (!apiKey) { showMsg('Please enter your Google API key', 'error'); return; }

    var aiKey = document.getElementById('aiKey').value.trim();
    var checked = [];
    document.querySelectorAll('input[name=cat]:checked').forEach(function(c) { checked.push(c.value); });
    if (checked.length === 0) { showMsg('Select at least one category', 'error'); return; }

    var maxPages = document.getElementById('maxPages').value;
    var btn = document.getElementById('extractBtn');
    btn.disabled = true;
    btn.textContent = 'Extracting...';
    document.getElementById('downloadBtn').style.display = 'none';
    document.getElementById('stats').style.display = 'none';
    document.getElementById('resultsCard').style.display = 'none';

    var aiMsg = aiKey ? ' with AI analysis' : ' (add Claude API key for AI features)';
    showMsg('Extracting' + aiMsg + '... This may take several minutes. Please wait...', 'loading');

    fetch('/api/extract', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ apiKey: apiKey, aiKey: aiKey, categories: checked, maxPages: parseInt(maxPages) })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.success) {
            showMsg('Success! Extracted ' + data.totalBusinesses + ' businesses (' + data.emailsVerified + ' verified, ' + data.emailsAI + ' AI-found, ' + data.emailsGuessed + ' guessed)', 'success');
            document.getElementById('downloadBtn').style.display = 'inline-block';

            document.getElementById('stats').style.display = 'flex';
            document.getElementById('sTotalBiz').textContent = data.totalBusinesses;
            document.getElementById('sPhones').textContent = data.phonesFound;
            document.getElementById('sVerified').textContent = data.emailsVerified;
            document.getElementById('sAiEmails').textContent = data.emailsAI;
            document.getElementById('sGuessed').textContent = data.emailsGuessed;
            document.getElementById('sWebsites').textContent = data.websitesFound;

            var tbody = document.getElementById('resultsBody');
            tbody.innerHTML = '';
            data.businesses.forEach(function(b, i) {
                var tr = document.createElement('tr');
                tr.innerHTML =
                    '<td>' + (i+1) + '</td>' +
                    '<td title="' + esc(b.company) + '">' + esc(b.company) + '</td>' +
                    '<td>' + esc(b.phone) + '</td>' +
                    '<td title="' + esc(b.email) + '">' + esc(b.email) + '</td>' +
                    '<td>' + badgeFor(b.email_type) + '</td>' +
                    '<td>' + confBadge(b.email_confidence) + '</td>' +
                    '<td>' + esc(b.contact_person) + '</td>' +
                    '<td title="' + esc(b.description) + '">' + esc(b.description) + '</td>' +
                    '<td>' + (b.website !== 'N/A' ? '<a href="' + esc(b.website) + '" target="_blank">Visit</a>' : 'N/A') + '</td>' +
                    '<td>' + b.rating + '</td>' +
                    '<td>' + b.reviews + '</td>';
                tbody.appendChild(tr);
            });
            document.getElementById('resultsCard').style.display = 'block';
        } else {
            showMsg('Error: ' + data.message, 'error');
        }
    })
    .catch(function(e) {
        showMsg('Error: ' + e.message, 'error');
    })
    .finally(function() {
        btn.disabled = false;
        btn.textContent = 'Extract Businesses';
    });
}
</script>
</body>
</html>
""".replace("CATEGORIES_PLACEHOLDER", CATS_JSON)


# ============================================================
#  ROUTES
# ============================================================
@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/api/extract", methods=["POST"])
def extract():
    global extracted_businesses, ai_api_key

    try:
        data = request.json
        api_key = data.get("apiKey", "").strip()
        ai_api_key = data.get("aiKey", "").strip()
        categories = data.get("categories", [])
        max_pages = min(data.get("maxPages", 2), 3)

        if not api_key:
            return jsonify({"success": False, "message": "Google API Key is required"})
        if not categories:
            return jsonify({"success": False, "message": "Select at least one category"})

        ai_mode = "ON" if ai_api_key else "OFF"
        print(f"\n[CONFIG] AI Mode: {ai_mode} | Categories: {len(categories)} | Pages: {max_pages}")

        # Step 1: Nearby Search
        seen_ids = set()
        raw_places = []
        for cat_key in categories:
            cat = CATEGORIES.get(cat_key)
            if not cat:
                continue
            print(f"[SEARCH] {cat['keyword']}")
            results = google_nearby_search(api_key, cat["keyword"], cat["type"], max_pages)
            for p in results:
                pid = p.get("place_id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    raw_places.append(p)
            print(f"  -> {len(results)} results, {len(raw_places)} unique total")

        if not raw_places:
            return jsonify({"success": False, "message": "No businesses found. Check API key and enable Places API."})

        # Step 2: Enrich
        print(f"[ENRICH] Processing {len(raw_places)} businesses (AI: {ai_mode})...")
        businesses = []
        workers = 4 if ai_api_key else 6
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(enrich_place, api_key, p): p for p in raw_places}
            for f in as_completed(futures):
                try:
                    biz = f.result()
                    if biz:
                        businesses.append(biz)
                        print(f"  [OK] {biz['company']} | {biz['phone']} | {biz['email']} ({biz['email_type']})")
                except Exception as exc:
                    print(f"  [WARN] {exc}")

        businesses.sort(key=lambda x: x.get("reviews", 0), reverse=True)
        extracted_businesses = businesses

        phones = sum(1 for b in businesses if b["phone"] != "N/A")
        emails_verified = sum(1 for b in businesses if b["email_type"] == "verified")
        emails_ai = sum(1 for b in businesses if b["email_type"] == "ai_extracted")
        emails_guessed = sum(1 for b in businesses if b["email_type"] == "guessed")
        websites = sum(1 for b in businesses if b["website"] != "N/A")

        print(f"\n[DONE] {len(businesses)} biz | {phones} phones | {emails_verified} verified | {emails_ai} AI | {emails_guessed} guessed\n")

        return jsonify({
            "success": True,
            "totalBusinesses": len(businesses),
            "phonesFound": phones,
            "emailsVerified": emails_verified,
            "emailsAI": emails_ai,
            "emailsGuessed": emails_guessed,
            "websitesFound": websites,
            "businesses": businesses,
        })

    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "Timeout - try again"})
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"success": False, "message": str(e)})


@app.route("/download")
def download():
    global extracted_businesses
    if not extracted_businesses:
        return "No data. Extract first.", 400

    si = StringIO()
    fields = ["company", "address", "phone", "email", "email_type", "email_confidence",
              "contact_person", "description", "services", "website", "rating", "reviews",
              "status", "maps_link"]
    writer = csv.DictWriter(si, fieldnames=fields)
    writer.writeheader()
    writer.writerows(extracted_businesses)

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=ai_business_data_{int(time.time())}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


# ============================================================
#  LAUNCH
# ============================================================
def open_browser():
    time.sleep(2)
    try:
        webbrowser.open("http://localhost:5000")
    except Exception:
        pass


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AI Business Data Extractor")
    print("  Google Places + Claude AI + Web Scraping")
    print("=" * 60)
    print("\n  Server running at http://localhost:5000")
    print("  Keep this window open!")
    print("=" * 60 + "\n")

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=5000, use_reloader=False, threaded=True)