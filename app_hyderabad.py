import json
import re
import csv
import time
import os
import threading
import webbrowser
from io import StringIO
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template_string, request, jsonify, make_response
import requests
from bs4 import BeautifulSoup

# Try importing apify-client
try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False
    print("[WARN] apify-client not installed. Run: pip install apify-client")

app = Flask(__name__)
extracted_businesses = []

# ============================================================
#  CONFIG
# ============================================================
HYDERABAD_LAT = 17.3850
HYDERABAD_LNG = 78.4867
SEARCH_RADIUS = 5000
HISTORY_FILE = "extracted_history.json"

HYDERABAD_AREAS = {
    "Central":            (17.3850, 78.4867),
    "Secunderabad":       (17.4000, 78.4750),
    "Kompally":           (17.4400, 78.4980),
    "Mehdipatnam":        (17.3600, 78.4740),
    "HITEC City":         (17.4435, 78.3772),
    "Gachibowli":        (17.4400, 78.3500),
    "Financial District": (17.4239, 78.3420),
    "Kondapur":           (17.4600, 78.3600),
    "Uppal":              (17.3950, 78.5500),
    "LB Nagar":           (17.3700, 78.5300),
    "Hayathnagar":        (17.3500, 78.5700),
    "Nacharam":           (17.4200, 78.5400),
    "Alwal":              (17.4800, 78.4900),
    "Bollaram":           (17.5100, 78.4700),
    "Bowenpally":         (17.4600, 78.4400),
    "Miyapur":            (17.4900, 78.3900),
    "Shamshabad":         (17.3200, 78.5000),
    "Attapur":            (17.3400, 78.4500),
    "Rajendranagar":      (17.3100, 78.4700),
    "Tolichowki":         (17.3600, 78.4200),
    "Patancheru":         (17.4100, 78.3200),
    "Narsingi":           (17.3900, 78.3600),
    "Manikonda":          (17.3700, 78.3900),
    "Begumpet":           (17.4300, 78.4500),
    "Banjara Hills":      (17.4150, 78.4350),
    "Ameerpet":           (17.4100, 78.4550),
    "Tarnaka":            (17.4050, 78.5000),
    "Dilsukhnagar":       (17.3800, 78.5100),
    "Kukatpally":         (17.4700, 78.4200),
    "Madhapur":           (17.4480, 78.3910),
}

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
JUNK_EMAILS = {"sentry@","wixpress","example.com","domain.com","email@","username@","test@","noreply@","no-reply@",".png",".jpg",".gif",".svg",".webp","google.com","gstatic","w3.org","schema.org","facebook.com","twitter.com","instagram.com","youtube.com"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
ai_api_key = ""

def is_junk_email(email):
    return any(j in email.lower() for j in JUNK_EMAILS)

# ============================================================
#  HISTORY
# ============================================================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"extracted_ids": [], "run_count": 0, "total_extracted": 0}

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception:
        pass

# ============================================================
#  APIFY — Google Maps Email Extractor
# ============================================================
def extract_with_apify(apify_token, search_queries, areas):
    """Use Apify Google Maps Email Extractor to get businesses with emails."""
    if not APIFY_AVAILABLE or not apify_token:
        return []

    client = ApifyClient(apify_token)
    all_businesses = []

    # Build search strings like "IT companies in HITEC City, Hyderabad"
    search_strings = []
    for query in search_queries:
        for area in areas:
            search_strings.append(f"{query} in {area}, Hyderabad, India")

    print(f"[APIFY] Starting extraction with {len(search_strings)} search queries...")

    try:
        run_input = {
            "searchStringsArray": search_strings,
            "maxCrawledPlacesPerSearch": 20,
            "language": "en",
            "deeperCityScrape": False,
            "scrapeEmails": True,
            "scrapeContacts": True,
        }

        # Try the main Google Maps Email Extractor
        actor_id = "compass/crawler-google-places"
        print(f"[APIFY] Running actor: {actor_id}")

        run = client.actor(actor_id).call(run_input=run_input, timeout_secs=300)

        if run and run.get("defaultDatasetId"):
            dataset = client.dataset(run["defaultDatasetId"])
            for item in dataset.iterate_items():
                biz = {
                    "company": item.get("title") or item.get("name") or "N/A",
                    "address": item.get("address") or item.get("street") or "N/A",
                    "phone": item.get("phone") or item.get("phoneUnformatted") or "N/A",
                    "email": ", ".join(item.get("emails", [])) if item.get("emails") else "N/A",
                    "email_type": "verified" if item.get("emails") else "N/A",
                    "email_confidence": "high" if item.get("emails") else "N/A",
                    "contact_person": "N/A",
                    "website": item.get("website") or "N/A",
                    "rating": item.get("totalScore") or item.get("rating") or "N/A",
                    "reviews": item.get("reviewsCount") or 0,
                    "status": "OPERATIONAL" if not item.get("permanentlyClosed") else "CLOSED",
                    "description": item.get("categoryName") or "N/A",
                    "services": item.get("categories", ["N/A"])[0] if item.get("categories") else "N/A",
                    "area": item.get("city") or item.get("neighborhood") or "N/A",
                    "maps_link": item.get("url") or "",
                    "social_facebook": item.get("facebookUrl") or "N/A",
                    "social_instagram": item.get("instagramUrl") or "N/A",
                    "social_twitter": item.get("twitterUrl") or "N/A",
                    "social_linkedin": item.get("linkedinUrl") or "N/A",
                    "source": "Apify",
                }
                all_businesses.append(biz)

            print(f"[APIFY] Got {len(all_businesses)} businesses from Apify")

    except Exception as e:
        print(f"[APIFY] Error: {e}")
        # Try alternative actor
        try:
            print("[APIFY] Trying alternative actor...")
            alt_input = {
                "searchStringsArray": search_strings[:10],
                "maxCrawledPlacesPerSearch": 10,
                "language": "en",
            }
            run = client.actor("lukaskrivka/google-maps-with-contact-details").call(run_input=alt_input, timeout_secs=300)
            if run and run.get("defaultDatasetId"):
                for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                    emails = []
                    if item.get("email"):
                        emails.append(item["email"])
                    if item.get("emails"):
                        emails.extend(item["emails"])
                    emails = [e for e in emails if e and not is_junk_email(e)]

                    biz = {
                        "company": item.get("title") or "N/A",
                        "address": item.get("address") or "N/A",
                        "phone": item.get("phone") or "N/A",
                        "email": ", ".join(emails) if emails else "N/A",
                        "email_type": "verified" if emails else "N/A",
                        "email_confidence": "high" if emails else "N/A",
                        "contact_person": "N/A",
                        "website": item.get("website") or "N/A",
                        "rating": item.get("totalScore") or "N/A",
                        "reviews": item.get("reviewsCount") or 0,
                        "status": "OPERATIONAL",
                        "description": item.get("categoryName") or "N/A",
                        "services": "N/A",
                        "area": "N/A",
                        "maps_link": item.get("url") or "",
                        "social_facebook": "N/A",
                        "social_instagram": "N/A",
                        "social_twitter": "N/A",
                        "social_linkedin": "N/A",
                        "source": "Apify",
                    }
                    all_businesses.append(biz)
                print(f"[APIFY] Got {len(all_businesses)} from alternative actor")
        except Exception as e2:
            print(f"[APIFY] Alternative also failed: {e2}")

    return all_businesses


# ============================================================
#  GOOGLE PLACES (existing)
# ============================================================
def google_nearby_search(api_key, lat, lng, keyword, place_type, max_pages=2):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {"location": f"{lat},{lng}", "radius": SEARCH_RADIUS, "keyword": keyword, "type": place_type, "key": api_key}
    results = []
    for _ in range(max_pages):
        resp = requests.get(url, params=params, timeout=15).json()
        if resp.get("status") not in ("OK", "ZERO_RESULTS"):
            break
        results.extend(resp.get("results", []))
        token = resp.get("next_page_token")
        if not token:
            break
        time.sleep(2)
        params = {"pagetoken": token, "key": api_key}
    return results

def google_place_details(api_key, place_id):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {"place_id": place_id, "fields": "formatted_phone_number,international_phone_number,website,formatted_address,url,business_status", "key": api_key}
    try:
        resp = requests.get(url, params=params, timeout=10).json()
        if resp.get("status") == "OK":
            return resp.get("result", {})
    except Exception:
        pass
    return {}

def scrape_emails_from_website(website_url, timeout=8):
    if not website_url:
        return []
    try:
        emails = set()
        try:
            resp = requests.get(website_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            emails |= {e for e in EMAIL_RE.findall(resp.text) if not is_junk_email(e)}
            soup = BeautifulSoup(resp.text, "html.parser")
            internal_links = set()
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                if any(kw in href for kw in ["contact", "about", "reach", "support", "enquiry"]):
                    if href.startswith("/"):
                        internal_links.add(website_url.rstrip("/") + href)
        except Exception:
            internal_links = set()
        for suffix in ["/contact", "/contact-us", "/about", "/about-us", "/support"]:
            internal_links.add(website_url.rstrip("/") + suffix)
        for link in list(internal_links)[:8]:
            try:
                sub = requests.get(link, headers=HEADERS, timeout=6, allow_redirects=True)
                if sub.status_code == 200:
                    emails |= {e for e in EMAIL_RE.findall(sub.text) if not is_junk_email(e)}
            except Exception:
                continue
        return list(emails)[:5]
    except Exception:
        return []

def generate_common_emails(website):
    if not website or website == "N/A":
        return []
    try:
        domain = urlparse(website).netloc
        if domain.startswith("www."):
            domain = domain[4:]
        if not domain or any(sd in domain for sd in ["google","facebook","instagram","youtube","justdial","indiamart"]):
            return []
        return [f"info@{domain}"]
    except Exception:
        return []

def enrich_google_place(api_key, place, area_name):
    details = google_place_details(api_key, place.get("place_id", "")) if place.get("place_id") else {}
    phone = details.get("formatted_phone_number") or details.get("international_phone_number") or "N/A"
    website = details.get("website", "")
    company_name = place.get("name", "N/A")

    emails = scrape_emails_from_website(website)
    email_type = "verified" if emails else "N/A"
    if not emails:
        guessed = generate_common_emails(website)
        if guessed:
            emails = guessed
            email_type = "guessed"

    return {
        "company": company_name,
        "address": details.get("formatted_address") or place.get("vicinity", "N/A"),
        "phone": phone,
        "email": ", ".join(emails) if emails else "N/A",
        "email_type": email_type,
        "email_confidence": "high" if email_type == "verified" else ("low" if email_type == "guessed" else "N/A"),
        "contact_person": "N/A",
        "website": website or "N/A",
        "rating": place.get("rating", "N/A"),
        "reviews": place.get("user_ratings_total", 0),
        "status": details.get("business_status", "N/A"),
        "description": "N/A",
        "services": "N/A",
        "area": area_name,
        "maps_link": details.get("url", ""),
        "social_facebook": "N/A",
        "social_instagram": "N/A",
        "social_twitter": "N/A",
        "social_linkedin": "N/A",
        "source": "Google Places",
    }


# ============================================================
#  HTML
# ============================================================
CATS_JSON = json.dumps({k: {"keyword": v["keyword"]} for k, v in CATEGORIES.items()})
AREAS_JSON = json.dumps(list(HYDERABAD_AREAS.keys()))

HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>AI Business Data Extractor</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);min-height:100vh;color:#e0e0e0}
.header{text-align:center;padding:35px 20px 15px}
.header h1{font-size:32px;background:linear-gradient(135deg,#667eea,#764ba2,#f093fb);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
.header p{color:#aaa;font-size:14px}
.ai-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;margin:6px 3px}
.main{max-width:1350px;margin:0 auto;padding:15px}
.card{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:25px;margin-bottom:20px}
.card h2{font-size:18px;margin-bottom:14px;color:#c9b1ff}
.form-row{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.form-group{flex:1;min-width:180px}
.form-group label{display:block;font-size:12px;font-weight:600;color:#bbb;margin-bottom:5px}
.form-group input,.form-group select{width:100%;padding:10px;border:1px solid rgba(255,255,255,0.15);border-radius:8px;background:rgba(255,255,255,0.07);color:#fff;font-size:13px;outline:none}
.form-group input:focus,.form-group select:focus{border-color:#667eea}
select option{background:#302b63;color:#fff}
.btn{padding:12px 26px;border:none;border-radius:8px;font-weight:700;font-size:14px;cursor:pointer;transition:.3s}
.btn-primary{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(102,126,234,.4)}
.btn-primary:disabled{opacity:.5;cursor:not-allowed;transform:none}
.btn-success{background:linear-gradient(135deg,#11998e,#38ef7d);color:#000;font-weight:700}
.btn-danger{background:linear-gradient(135deg,#e74c3c,#c0392b);color:#fff}
.btn-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}
.stat-box{flex:1;min-width:90px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:12px;text-align:center}
.stat-box .num{font-size:20px;font-weight:800;background:linear-gradient(135deg,#667eea,#f093fb);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat-box .lbl{font-size:9px;color:#999;margin-top:3px}
.msg{margin-top:14px;padding:12px;border-radius:8px;font-size:13px;display:none}
.msg.show{display:block}
.msg.error{background:rgba(220,53,69,.15);color:#ff6b6b;border:1px solid rgba(220,53,69,.25)}
.msg.success{background:rgba(56,239,125,.1);color:#38ef7d;border:1px solid rgba(56,239,125,.2)}
.msg.loading{background:rgba(102,126,234,.1);color:#a5b4fc;border:1px solid rgba(102,126,234,.2)}
.table-wrap{overflow-x:auto;margin-top:14px;border-radius:10px;border:1px solid rgba(255,255,255,.08)}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:rgba(102,126,234,.25);color:#c9b1ff;padding:8px 6px;text-align:left;white-space:nowrap;font-weight:700;position:sticky;top:0}
td{padding:6px;border-bottom:1px solid rgba(255,255,255,.06);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr:hover td{background:rgba(255,255,255,.04)}
a{color:#667eea;text-decoration:none}
.checkbox-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:6px;margin-top:6px}
.checkbox-grid label{display:flex;align-items:center;gap:5px;font-size:12px;color:#ccc;cursor:pointer;padding:5px 8px;border-radius:6px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08)}
.checkbox-grid label:hover{background:rgba(102,126,234,.12)}
.checkbox-grid input[type=checkbox]{accent-color:#667eea}
.help-text{font-size:11px;color:#888;margin-top:4px}
.badge{display:inline-block;padding:2px 6px;border-radius:5px;font-size:9px;font-weight:700}
.badge-verified{background:rgba(56,239,125,.15);color:#38ef7d}
.badge-guessed{background:rgba(255,193,7,.15);color:#ffc107}
.badge-google{background:rgba(66,133,244,.2);color:#4285f4}
.badge-apify{background:rgba(0,204,153,.2);color:#00cc99}
.optional-tag{font-size:9px;color:#888;background:rgba(255,255,255,.06);padding:2px 5px;border-radius:4px;margin-left:3px}
.footer{text-align:center;padding:25px;color:#555;font-size:11px}
.section-label{font-size:13px;font-weight:700;color:#c9b1ff;margin-bottom:4px;display:block}
</style>
</head>
<body>
<div class="header">
    <h1>AI Business Data Extractor</h1>
    <p>Multi-source extraction with emails, phones, and social media</p>
    <div class="ai-badge">Google Maps</div>
    <div class="ai-badge">Apify</div>
    <div class="ai-badge">Web Scraping</div>
</div>
<div class="main">
    <div class="card">
        <h2>Configuration</h2>
        <div class="form-row">
            <div class="form-group">
                <label>Google Places API Key <span class="optional-tag">Optional if using Apify</span></label>
                <input type="password" id="apiKey" placeholder="Google API key" autocomplete="off">
                <div class="help-text"><a href="https://console.cloud.google.com" target="_blank">Get key</a></div>
            </div>
            <div class="form-group">
                <label>Apify API Token <span class="optional-tag">Recommended</span></label>
                <input type="password" id="apifyKey" placeholder="Apify token — best for emails" autocomplete="off">
                <div class="help-text"><a href="https://console.apify.com/account/integrations" target="_blank">Get token</a> — Free $5/month</div>
            </div>
            <div class="form-group">
                <label>Claude AI Key <span class="optional-tag">Optional</span></label>
                <input type="password" id="aiKey" placeholder="Optional — AI features" autocomplete="off">
            </div>
        </div>

        <label class="section-label">Select Areas to Search</label>
        <div class="checkbox-grid" id="areaGrid"></div>
        <div class="help-text" style="margin-top:6px"><a href="#" onclick="toggleAreas(true);return false">Select All</a> | <a href="#" onclick="toggleAreas(false);return false">Deselect All</a></div>

        <br>
        <label class="section-label">Select Business Categories</label>
        <div class="checkbox-grid" id="catGrid"></div>

        <div class="btn-row">
            <button class="btn btn-primary" id="extractBtn" onclick="startExtraction()">Extract NEW Businesses</button>
            <button class="btn btn-success" id="downloadBtn" onclick="location.href='/download'" style="display:none">Download CSV</button>
            <button class="btn btn-danger" onclick="if(confirm('Clear all history?')){fetch('/api/reset',{method:'POST'}).then(function(){location.reload()})}">Reset History</button>
        </div>

        <div class="msg" id="msg"></div>

        <div class="stats" id="stats" style="display:none">
            <div class="stat-box"><div class="num" id="sNew">0</div><div class="lbl">New Businesses</div></div>
            <div class="stat-box"><div class="num" id="sSkipped">0</div><div class="lbl">Skipped</div></div>
            <div class="stat-box"><div class="num" id="sPhones">0</div><div class="lbl">Phones</div></div>
            <div class="stat-box"><div class="num" id="sEmails">0</div><div class="lbl">Emails</div></div>
            <div class="stat-box"><div class="num" id="sApify">0</div><div class="lbl">From Apify</div></div>
            <div class="stat-box"><div class="num" id="sGoogle">0</div><div class="lbl">From Google</div></div>
        </div>
    </div>

    <div class="card" id="resultsCard" style="display:none">
        <h2>Extracted Businesses (NEW only)</h2>
        <div class="table-wrap">
            <table><thead><tr>
                <th>#</th><th>Company</th><th>Phone</th><th>Email</th><th>Email Type</th>
                <th>Website</th><th>Area</th><th>Rating</th><th>Reviews</th><th>Source</th>
                <th>Facebook</th><th>LinkedIn</th>
            </tr></thead><tbody id="resultsBody"></tbody></table>
        </div>
    </div>
</div>
<div class="footer">AI Business Data Extractor — Google Places + Apify + Web Scraping</div>

<script>
var cats=CATEGORIES_PLACEHOLDER;
var areas=AREAS_PLACEHOLDER;
var catGrid=document.getElementById('catGrid');
Object.entries(cats).forEach(function(e){var k=e[0],v=e[1];var l=document.createElement('label');var chk=['it_companies','software','startups'].indexOf(k)>=0?'checked':'';l.innerHTML='<input type="checkbox" name="cat" value="'+k+'" '+chk+'> '+v.keyword;catGrid.appendChild(l)});
var areaGrid=document.getElementById('areaGrid');
areas.forEach(function(a,i){var l=document.createElement('label');var chk=i<10?'checked':'';l.innerHTML='<input type="checkbox" name="area" value="'+a+'" '+chk+'> '+a;areaGrid.appendChild(l)});

function toggleAreas(on){document.querySelectorAll('input[name=area]').forEach(function(c){c.checked=on})}
function showMsg(t,c){var m=document.getElementById('msg');m.className='msg show '+c;m.innerHTML=t}
function esc(s){if(!s)return'';var d=document.createElement('div');d.textContent=String(s);return d.innerHTML}

function startExtraction(){
    var apiKey=document.getElementById('apiKey').value.trim();
    var apifyKey=document.getElementById('apifyKey').value.trim();
    var aiKey=document.getElementById('aiKey').value.trim();
    if(!apiKey && !apifyKey){showMsg('Enter at least one key: Google API or Apify token','error');return}
    var checkedCats=[];document.querySelectorAll('input[name=cat]:checked').forEach(function(c){checkedCats.push(c.value)});
    var checkedAreas=[];document.querySelectorAll('input[name=area]:checked').forEach(function(c){checkedAreas.push(c.value)});
    if(checkedCats.length===0){showMsg('Select at least one category','error');return}
    if(checkedAreas.length===0){showMsg('Select at least one area','error');return}
    var btn=document.getElementById('extractBtn');btn.disabled=true;btn.textContent='Extracting...';
    document.getElementById('downloadBtn').style.display='none';
    document.getElementById('stats').style.display='none';
    document.getElementById('resultsCard').style.display='none';
    var sources=[];if(apiKey)sources.push('Google');if(apifyKey)sources.push('Apify');
    showMsg('Extracting from '+sources.join(' + ')+' across '+checkedAreas.length+' areas... This may take several minutes...','loading');

    fetch('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({apiKey:apiKey,apifyKey:apifyKey,aiKey:aiKey,categories:checkedCats,areas:checkedAreas})
    }).then(function(r){return r.json()}).then(function(d){
        if(d.success){
            showMsg('Found <b>'+d.newBusinesses+'</b> NEW businesses! ('+d.skipped+' duplicates skipped) | Apify: '+d.fromApify+' | Google: '+d.fromGoogle,'success');
            document.getElementById('downloadBtn').style.display='inline-block';
            document.getElementById('stats').style.display='flex';
            document.getElementById('sNew').textContent=d.newBusinesses;
            document.getElementById('sSkipped').textContent=d.skipped;
            document.getElementById('sPhones').textContent=d.phonesFound;
            document.getElementById('sEmails').textContent=d.emailsFound;
            document.getElementById('sApify').textContent=d.fromApify;
            document.getElementById('sGoogle').textContent=d.fromGoogle;
            var tbody=document.getElementById('resultsBody');tbody.innerHTML='';
            d.businesses.forEach(function(b,i){var tr=document.createElement('tr');
                var srcBadge=b.source==='Apify'?'<span class="badge badge-apify">Apify</span>':'<span class="badge badge-google">Google</span>';
                var typeBadge=b.email_type==='verified'?'<span class="badge badge-verified">Verified</span>':b.email_type==='guessed'?'<span class="badge badge-guessed">Guessed</span>':'-';
                tr.innerHTML='<td>'+(i+1)+'</td><td title="'+esc(b.company)+'">'+esc(b.company)+'</td><td>'+esc(b.phone)+'</td><td title="'+esc(b.email)+'">'+esc(b.email)+'</td><td>'+typeBadge+'</td><td>'+(b.website!=='N/A'?'<a href="'+esc(b.website)+'" target="_blank">Visit</a>':'N/A')+'</td><td>'+esc(b.area)+'</td><td>'+b.rating+'</td><td>'+b.reviews+'</td><td>'+srcBadge+'</td><td>'+(b.social_facebook!=='N/A'?'<a href="'+esc(b.social_facebook)+'" target="_blank">FB</a>':'—')+'</td><td>'+(b.social_linkedin!=='N/A'?'<a href="'+esc(b.social_linkedin)+'" target="_blank">LI</a>':'—')+'</td>';
                tbody.appendChild(tr)});
            document.getElementById('resultsCard').style.display='block';
        }else{showMsg('Error: '+d.message,'error')}
    }).catch(function(e){showMsg('Error: '+e.message,'error')})
    .finally(function(){btn.disabled=false;btn.textContent='Extract NEW Businesses'});
}
</script>
</body></html>
""".replace("CATEGORIES_PLACEHOLDER", CATS_JSON).replace("AREAS_PLACEHOLDER", AREAS_JSON)


# ============================================================
#  ROUTES
# ============================================================
@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/api/reset", methods=["POST"])
def reset():
    save_history({"extracted_ids": [], "run_count": 0, "total_extracted": 0})
    return jsonify({"success": True})

@app.route("/api/extract", methods=["POST"])
def extract():
    global extracted_businesses, ai_api_key

    try:
        data = request.json
        api_key = data.get("apiKey", "").strip()
        apify_key = data.get("apifyKey", "").strip()
        ai_api_key = data.get("aiKey", "").strip()
        categories = data.get("categories", [])
        selected_areas = data.get("areas", [])

        if not api_key and not apify_key:
            return jsonify({"success": False, "message": "Enter at least one: Google API key or Apify token"})

        history = load_history()
        known_ids = set(history.get("extracted_ids", []))
        all_businesses = []
        skipped = 0

        # ---- SOURCE 1: APIFY ----
        if apify_key:
            search_queries = [CATEGORIES[c]["keyword"] for c in categories if c in CATEGORIES]
            apify_results = extract_with_apify(apify_key, search_queries, selected_areas)
            for biz in apify_results:
                biz_id = f"apify_{biz['company']}_{biz['address']}"
                if biz_id in known_ids:
                    skipped += 1
                    continue
                known_ids.add(biz_id)
                all_businesses.append(biz)

        # ---- SOURCE 2: GOOGLE PLACES ----
        if api_key:
            seen_pids = set()
            raw_google = []
            for area_name in selected_areas:
                coords = HYDERABAD_AREAS.get(area_name)
                if not coords:
                    continue
                lat, lng = coords
                for cat_key in categories:
                    cat = CATEGORIES.get(cat_key)
                    if not cat:
                        continue
                    print(f"  [Google] {area_name} -> {cat['keyword']}")
                    results = google_nearby_search(api_key, lat, lng, cat["keyword"], cat["type"], 1)
                    for p in results:
                        pid = p.get("place_id")
                        if not pid or pid in seen_pids or pid in known_ids:
                            if pid in known_ids:
                                skipped += 1
                            continue
                        seen_pids.add(pid)
                        p["_area"] = area_name
                        raw_google.append(p)

            if raw_google:
                print(f"  [Google] Enriching {len(raw_google)} businesses...")
                with ThreadPoolExecutor(max_workers=6) as pool:
                    futures = {pool.submit(enrich_google_place, api_key, p, p.get("_area", "")): p for p in raw_google}
                    for f in as_completed(futures):
                        try:
                            biz = f.result()
                            if biz:
                                known_ids.add(futures[f].get("place_id", ""))
                                all_businesses.append(biz)
                        except Exception as exc:
                            print(f"  [WARN] {exc}")

        # Sort and save
        all_businesses.sort(key=lambda x: x.get("reviews", 0), reverse=True)
        extracted_businesses = all_businesses

        # Update history
        history["extracted_ids"] = list(known_ids)
        history["run_count"] = history.get("run_count", 0) + 1
        history["total_extracted"] = len(known_ids)
        save_history(history)

        phones = sum(1 for b in all_businesses if b["phone"] != "N/A")
        emails = sum(1 for b in all_businesses if b["email"] != "N/A")
        from_apify = sum(1 for b in all_businesses if b.get("source") == "Apify")
        from_google = sum(1 for b in all_businesses if b.get("source") == "Google Places")

        print(f"\n[DONE] {len(all_businesses)} new | {skipped} skipped | {from_apify} Apify | {from_google} Google\n")

        return jsonify({
            "success": True,
            "newBusinesses": len(all_businesses),
            "skipped": skipped,
            "phonesFound": phones,
            "emailsFound": emails,
            "fromApify": from_apify,
            "fromGoogle": from_google,
            "businesses": all_businesses,
        })

    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"success": False, "message": str(e)})


@app.route("/download")
def download():
    global extracted_businesses
    if not extracted_businesses:
        return "No data.", 400
    si = StringIO()
    fields = ["company","address","phone","email","email_type","email_confidence","contact_person",
              "website","rating","reviews","status","description","services","area","maps_link",
              "social_facebook","social_instagram","social_twitter","social_linkedin","source"]
    writer = csv.DictWriter(si, fieldnames=fields)
    writer.writeheader()
    writer.writerows(extracted_businesses)
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=business_data_{int(time.time())}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


def open_browser():
    time.sleep(2)
    try:
        webbrowser.open("http://localhost:5000")
    except Exception:
        pass

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AI Business Data Extractor")
    print("  Google Places + Apify + Web Scraping")
    print("=" * 60)
    print(f"  Apify client: {'Available' if APIFY_AVAILABLE else 'NOT installed (pip install apify-client)'}")
    print(f"\n  Server: http://localhost:5000")
    print("  Keep this window open!")
    print("=" * 60 + "\n")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=5000, use_reloader=False, threaded=True)
