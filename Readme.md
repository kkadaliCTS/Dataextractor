# 🤖 AI Business Data Extractor

AI-powered tool to extract business data (company name, phone, email, website, rating, reviews) from any city using Google Maps + Claude AI + Web Scraping.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-Web_App-green.svg)
![AI](https://img.shields.io/badge/Claude_AI-Powered-purple.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## ✨ Features

- **15 Business Categories** — IT companies, software firms, startups, restaurants, hospitals, hotels, and more
- **4-Layer Email Finding:**
  - 🔍 Layer 1: Deep website scraping (homepage + contact/about pages + mailto links)
  - 🔍 Layer 2: Google search for company email
  - 🤖 Layer 3: AI-powered extraction using Claude (reads and understands webpage content)
  - 📧 Layer 4: Smart email pattern guessing (info@domain.com)
- **Phone Numbers** from Google Place Details API
- **AI Features** (optional, with Claude API key):
  - Intelligent contact extraction from messy webpage text
  - Email validation with confidence scoring (High/Medium/Low)
  - Auto-generated business descriptions
  - Contact person detection
- **CSV Export** — Download all data in Excel-compatible format
- **Duplicate Removal** — Only unique businesses in results
- **Beautiful Dark UI** with live stats dashboard

---

## 📸 Screenshots

### Main Interface
- Clean dark UI with category selection
- Google API key + optional Claude AI key inputs
- Real-time extraction stats

### Results Table
- Company, Phone, Email, Source badge (Verified/AI Found/Guessed)
- Confidence score, Contact person, AI Description
- Clickable website links

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+** — [Download here](https://www.python.org/downloads/)
  - ⚠️ Check **"Add Python to PATH"** during installation
- **Google Places API Key** — [Get it here](https://console.cloud.google.com) (Free $200/month credit)
- **Claude AI API Key** (Optional) — [Get it here](https://console.anthropic.com)

### Installation

#### Option 1: One-Click (Windows)
```
1. Download this repository (Code → Download ZIP → Extract)
2. Double-click run.bat
3. Browser opens automatically at http://localhost:5000
```

#### Option 2: Manual Setup
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/ai-business-extractor.git
cd ai-business-extractor

# Install dependencies
pip install flask requests beautifulsoup4

# Run the application
python app_hyderabad.py
```

Then open your browser at `http://localhost:5000`

---

## 📖 How to Use

1. **Paste your Google Places API Key** (required)
2. **Paste your Claude AI API Key** (optional — enables smart AI features)
3. **Select business categories** you want to extract
4. **Choose max pages** per category (1-3)
5. Click **Extract Businesses**
6. Wait for extraction to complete
7. Click **Download CSV** to get your data

---

## 🔑 Getting API Keys

### Google Places API Key (Required)
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Go to **APIs & Services** → **Library**
4. Search **"Places API"** and **Enable** it
5. Go to **APIs & Services** → **Credentials**
6. Click **Create Credentials** → **API Key**
7. Copy the key

> Google provides **$200 free credit per month** — more than enough for this tool.

### Claude AI API Key (Optional)
1. Go to [Anthropic Console](https://console.anthropic.com)
2. Create an account
3. Go to **API Keys**
4. Create a new key and copy it

> The AI key enables smarter email extraction, validation, and business descriptions.

---

## 📊 What Data You Get

| Column | Description | Source |
|--------|-------------|--------|
| company | Business name | Google Maps |
| address | Full address | Google Place Details |
| phone | Phone number | Google Place Details |
| email | Email address(es) | Web Scraping + AI |
| email_type | verified / ai_extracted / guessed | System |
| email_confidence | high / medium / low | Claude AI |
| contact_person | Name of contact person | Claude AI |
| description | What the business does | Claude AI |
| services | Main services offered | Claude AI |
| website | Business website URL | Google Place Details |
| rating | Google rating (1-5) | Google Maps |
| reviews | Number of Google reviews | Google Maps |
| status | OPERATIONAL / CLOSED | Google Place Details |
| maps_link | Google Maps URL | Google Maps |

---

## 📈 Usage Limits

| Usage Level | Categories | Businesses Per Run | Per Month |
|-------------|-----------|-------------------|-----------|
| Light | 3 categories, 1 page | ~60 | ~1,800 |
| Medium | 5 categories, 2 pages | ~150-200 | ~6,000 |
| Heavy | 15 categories, 3 pages | ~400-900 | ~15,000 |

All within Google's free $200/month credit.

---

## 🏗️ Tech Stack

- **Backend:** Python 3, Flask
- **AI Engine:** Claude AI (Anthropic API)
- **Data Sources:** Google Places API, Web Scraping
- **Frontend:** HTML, CSS, JavaScript
- **Email Finding:** BeautifulSoup, Regex, AI Extraction

---

## 📁 Project Structure

```
ai-business-extractor/
├── run.bat              # Windows one-click launcher
├── app_hyderabad.py     # Main application
└── README.md            # This file
```

---

## ⚙️ Configuration

To change the target city, edit these lines in `app_hyderabad.py`:

```python
HYDERABAD_LAT = 17.3850    # Change to your city latitude
HYDERABAD_LNG = 78.4867    # Change to your city longitude
SEARCH_RADIUS = 15000      # Search radius in metres (max 50000)
```

To add new business categories, add to the `CATEGORIES` dictionary:

```python
"your_category": {"keyword": "search term", "type": "establishment"},
```

---

## ⚠️ Legal & Compliance

- All data sourced from publicly available information
- Google Places API usage follows Google's Terms of Service
- Emails collected from publicly visible website pages
- Follow anti-spam laws when using extracted emails for outreach
- Tool intended for legitimate business research purposes

---

## 🤝 Contributing

Feel free to open issues or submit pull requests for improvements.

---

## 📄 License

This project is licensed under the MIT License.