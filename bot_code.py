import os
import re
import telebot
import anthropic
import base64
import requests
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from newspaper import Article

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SHEET_ID = "1UrZdID6UMA8Y_bAFuGeHAoXevHjq_4nWf0eYlAKoDLw"
CREDENTIALS_FILE = "credentials.json"

# ─── Google Sheets ─────────────────────────────────────────────────────────────

def get_workbook():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def get_or_create_sheet(workbook, name, headers):
    try:
        sheet = workbook.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        sheet = workbook.add_worksheet(title=name, rows=1000, cols=len(headers))
        sheet.append_row(headers)
    if sheet.row_count == 0 or sheet.cell(1, 1).value is None:
        sheet.append_row(headers)
    return sheet

def save_to_sheet(workbook, category, data):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if category == "person":
        sheet = get_or_create_sheet(workbook, "Persons", [
            "Timestamp", "Full Name", "Title / Role", "Company",
            "Location", "Email", "Phone", "LinkedIn", "Instagram",
            "Bio / About", "Notes"
        ])
        sheet.append_row([
            timestamp,
            data.get("full_name", ""),
            data.get("title", ""),
            data.get("company", ""),
            data.get("location", ""),
            data.get("email", ""),
            data.get("phone", ""),
            data.get("linkedin", ""),
            data.get("instagram", ""),
            data.get("bio", ""),
            data.get("notes", "")
        ])

    elif category == "company":
        sheet = get_or_create_sheet(workbook, "Companies", [
            "Timestamp", "Company Name", "Industry", "Website",
            "Location", "Size", "Description", "Key People",
            "Contact Info", "Notes"
        ])
        sheet.append_row([
            timestamp,
            data.get("company_name", ""),
            data.get("industry", ""),
            data.get("website", ""),
            data.get("location", ""),
            data.get("size", ""),
            data.get("description", ""),
            data.get("key_people", ""),
            data.get("contact_info", ""),
            data.get("notes", "")
        ])

    elif category == "job":
        sheet = get_or_create_sheet(workbook, "Jobs", [
            "Timestamp", "Job Title", "Company", "Location",
            "Salary", "Job Type", "Experience Required",
            "Key Skills", "Apply Link", "Deadline", "Notes"
        ])
        sheet.append_row([
            timestamp,
            data.get("job_title", ""),
            data.get("company", ""),
            data.get("location", ""),
            data.get("salary", ""),
            data.get("job_type", ""),
            data.get("experience", ""),
            data.get("skills", ""),
            data.get("apply_link", ""),
            data.get("deadline", ""),
            data.get("notes", "")
        ])

    elif category == "event":
        sheet = get_or_create_sheet(workbook, "Events", [
            "Timestamp", "Event Name", "Date", "Time",
            "Location", "Organizer", "Price", "Registration Link",
            "Description", "Participants", "Notes"
        ])
        sheet.append_row([
            timestamp,
            data.get("event_name", ""),
            data.get("date", ""),
            data.get("time", ""),
            data.get("location", ""),
            data.get("organizer", ""),
            data.get("price", ""),
            data.get("registration_link", ""),
            data.get("description", ""),
            data.get("participants", ""),
            data.get("notes", "")
        ])

    elif category == "article":
        sheet = get_or_create_sheet(workbook, "Reading List", [
            "Timestamp", "Title", "Author", "Source / Publication",
            "Topic", "Summary", "Key Takeaways", "Link", "Notes"
        ])
        sheet.append_row([
            timestamp,
            data.get("title", ""),
            data.get("author", ""),
            data.get("source", ""),
            data.get("topic", ""),
            data.get("summary", ""),
            data.get("key_takeaways", ""),
            data.get("link", ""),
            data.get("notes", "")
        ])

    elif category == "data":
        sheet = get_or_create_sheet(workbook, "Data", [
            "Timestamp", "Summary", "Key Info", "Details",
            "Personal Info Found", "Source / Context"
        ])
        sheet.append_row([
            timestamp,
            data.get("summary", ""),
            data.get("key_info", ""),
            data.get("details", ""),
            data.get("personal_info", ""),
            data.get("source", "")
        ])

# ─── Claude prompt ─────────────────────────────────────────────────────────────

CLASSIFY_PROMPT = """Analyze the content and respond ONLY with a JSON object, no extra text.

Classify into one of these categories:
- "person" → LinkedIn/Instagram/social profile of an individual
- "company" → LinkedIn/website/page of a company or organization
- "job" → job posting or job listing
- "event" → event, conference, meetup, or gathering
- "article" → article, blog post, newsletter, social media post, or content to read later
- "data" → anything else with lots of information

Then extract fields based on category:

If "person":
{
  "category": "person",
  "full_name": "",
  "title": "",
  "company": "",
  "location": "",
  "email": "",
  "phone": "",
  "linkedin": "",
  "instagram": "",
  "bio": "",
  "notes": ""
}

If "company":
{
  "category": "company",
  "company_name": "",
  "industry": "",
  "website": "",
  "location": "",
  "size": "",
  "description": "",
  "key_people": "",
  "contact_info": "",
  "notes": ""
}

If "job":
{
  "category": "job",
  "job_title": "",
  "company": "",
  "location": "",
  "salary": "",
  "job_type": "full-time/part-time/freelance/etc",
  "experience": "",
  "skills": "",
  "apply_link": "",
  "deadline": "",
  "notes": ""
}

If "event":
{
  "category": "event",
  "event_name": "",
  "date": "",
  "time": "",
  "location": "",
  "organizer": "",
  "price": "",
  "registration_link": "",
  "description": "",
  "participants": "List ALL participants, speakers, hosts, or attendees visible — comma separated, include every single name you can see",
  "notes": ""
}

If "article":
{
  "category": "article",
  "title": "",
  "author": "",
  "source": "",
  "topic": "",
  "summary": "",
  "key_takeaways": "",
  "link": "",
  "notes": ""
}

If "data":
{
  "category": "data",
  "summary": "",
  "key_info": "",
  "details": "",
  "personal_info": "any names, emails, phones found — leave empty if none",
  "source": ""
}"""

# ─── Helpers ───────────────────────────────────────────────────────────────────

def extract_url(text):
    pattern = r'https?://[^\s]+'
    match = re.search(pattern, text)
    return match.group(0) if match else None

def scrape_url(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return {
            "title": article.title,
            "authors": ", ".join(article.authors),
            "text": article.text[:4000],
            "url": url
        }
    except Exception:
        # Fallback: plain requests + strip HTML
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.get(url, headers=headers, timeout=10)
            text = re.sub(r'<[^>]+>', ' ', res.text)
            text = re.sub(r'\s+', ' ', text).strip()
            return {"title": "", "authors": "", "text": text[:4000], "url": url}
        except Exception:
            return None

def parse_claude_response(raw_text):
    try:
        raw = raw_text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {
            "category": "data",
            "summary": raw_text,
            "key_info": "—",
            "details": "—",
            "personal_info": "—",
            "source": "—"
        }

def build_reply(category, data):
    sheet_map = {
        "person": "Persons", "company": "Companies", "job": "Jobs",
        "event": "Events", "article": "Reading List", "data": "Data"
    }
    emoji_map = {
        "person": "👤", "company": "🏢", "job": "💼",
        "event": "🗓️", "article": "📰", "data": "📊"
    }
    emoji = emoji_map.get(category, "📋")
    sheet_name = sheet_map.get(category, "Data")

    if category == "person":
        return (
            f"{emoji} *Saved to {sheet_name}!*\n\n"
            f"👤 *Name:* {data.get('full_name', '—')}\n"
            f"💼 *Role:* {data.get('title', '—')}\n"
            f"🏢 *Company:* {data.get('company', '—')}\n"
            f"📍 *Location:* {data.get('location', '—')}\n"
            f"📞 *Contact:* {data.get('email') or data.get('phone') or '—'}"
        )
    elif category == "company":
        return (
            f"{emoji} *Saved to {sheet_name}!*\n\n"
            f"🏢 *Company:* {data.get('company_name', '—')}\n"
            f"🏭 *Industry:* {data.get('industry', '—')}\n"
            f"📍 *Location:* {data.get('location', '—')}\n"
            f"👥 *Size:* {data.get('size', '—')}"
        )
    elif category == "job":
        return (
            f"{emoji} *Saved to {sheet_name}!*\n\n"
            f"💼 *Role:* {data.get('job_title', '—')}\n"
            f"🏢 *Company:* {data.get('company', '—')}\n"
            f"📍 *Location:* {data.get('location', '—')}\n"
            f"💰 *Salary:* {data.get('salary') or '—'}\n"
            f"🛠️ *Skills:* {data.get('skills') or '—'}"
        )
    elif category == "event":
        participants = data.get("participants", "")
        participant_count = len(participants.split(",")) if participants else 0
        participant_preview = participants[:200] + "..." if len(participants) > 200 else participants
        return (
            f"{emoji} *Saved to {sheet_name}!*\n\n"
            f"🎯 *Event:* {data.get('event_name', '—')}\n"
            f"📅 *Date:* {data.get('date', '—')}\n"
            f"⏰ *Time:* {data.get('time') or '—'}\n"
            f"📍 *Location:* {data.get('location', '—')}\n"
            f"💵 *Price:* {data.get('price') or 'Free'}\n"
            f"👥 *Participants ({participant_count}):* {participant_preview or '—'}"
        )
    elif category == "article":
        return (
            f"{emoji} *Saved to Reading List!*\n\n"
            f"📰 *Title:* {data.get('title', '—')}\n"
            f"✍️ *Author:* {data.get('author') or '—'}\n"
            f"🌐 *Source:* {data.get('source', '—')}\n"
            f"💡 *Takeaways:* {data.get('key_takeaways') or '—'}"
        )
    else:
        return (
            f"{emoji} *Saved to {sheet_name}!*\n\n"
            f"📝 *Summary:* {data.get('summary', '—')}\n"
            f"🔑 *Key Info:* {data.get('key_info', '—')}\n"
            f"👤 *Personal Info:* {data.get('personal_info') or 'None found'}"
        )

# ─── Handlers ──────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.reply_to(message, "📸 Analyzing screenshot...")

    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
    img_data = requests.get(file_url).content
    img_base64 = base64.b64encode(img_data).decode('utf-8')

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img_base64
                    }
                },
                {"type": "text", "text": CLASSIFY_PROMPT}
            ]
        }]
    )

    data = parse_claude_response(response.content[0].text)
    workbook = get_workbook()
    category = data.get("category", "data")
    save_to_sheet(workbook, category, data)
    bot.reply_to(message, build_reply(category, data), parse_mode="Markdown")


@bot.message_handler(func=lambda message: extract_url(message.text) is not None)
def handle_link(message):
    url = extract_url(message.text)
    bot.reply_to(message, "🔗 Fetching link...")

    scraped = scrape_url(url)
    if not scraped:
        bot.reply_to(message, "❌ Could not fetch that link. It might require a login or block bots.")
        return

    content_text = f"""URL: {scraped['url']}
Title: {scraped['title']}
Authors: {scraped['authors']}

Content:
{scraped['text']}

{CLASSIFY_PROMPT}"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": content_text
        }]
    )

    data = parse_claude_response(response.content[0].text)

    # Make sure the URL is always saved regardless of category
    data.setdefault("link", url)
    data.setdefault("apply_link", url)
    data.setdefault("registration_link", url)

    workbook = get_workbook()
    category = data.get("category", "data")
    save_to_sheet(workbook, category, data)
    bot.reply_to(message, build_reply(category, data), parse_mode="Markdown")


bot.polling()