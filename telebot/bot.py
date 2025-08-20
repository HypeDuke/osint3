import os
import requests
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import threading
from flask import Flask
from telegram import InputFile
import random
from io import BytesIO
from datetime import datetime



# Load biến môi trường
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CRAWLER_API = os.getenv("CRAWLER_API", "http://crawler:5000")
THEHARVESTER_API = os.getenv("THEHARVESTER_API", "http://theharvester_api:5100/query")
TWEETFEED_API = os.getenv("TWEETFEED_API", "https://api.tweetfeed.live/v1/today")
SOCIAL_API = os.getenv("SOCIAL_API", "http://social_scraper:5200/social")

DEFAULT_SOURCES = (
    "api_endpoints,baidu,,builtwith,brave,censys,"
    "certspotter,criminalip,crtsh,dnsdumpster,duckduckgo,fullhunt,"
    "github-code,hudsonrock,hunter,hunterhow,"
    "intelx,linkedin,linkedin_links,netcraft,netlas,omnisint,"
    "otx,qwant,rapiddns,"
    "securityTrails,shodan,subdomaincenter,"
    "subdomainfinderc99,sublist3r,threatcrowd,threatminer,tomba,urlscan,"
    "virustotal,whoisxml,yahoo,zoomeye,zoomeyeapi"
)
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)


MAX_MSG_LENGTH = 3500  # Telegram giới hạn độ dài tin nhắn

'''
# ---- Helpers ----
def send_text_or_file(update: Update, text: str, filename: str):
    """Gửi text, nếu dài hơn giới hạn thì lưu ra file và gửi."""
    if len(text) <= MAX_MSG_LENGTH:
        update.message.reply_text(text)
    else:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmp:
            tmp.write(text)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            update.message.reply_document(InputFile(f, filename=filename))
        os.remove(tmp_path)
'''

# Endpoint Flask kiểm tra trạng thái bot
@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200

# Lệnh /search
def search_cmd(update: Update, context):
    query = ' '.join(context.args)
    if not query:
        update.message.reply_text("Usage: /search <query>")
        return

    chat_id = update.message.chat_id
    update.message.reply_text(f"Searching for: {query} ...")

    try:
        r = requests.get(f"{CRAWLER_API}/search", params={"q": query, "size": 50}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            total = data.get("total", {}).get("value", 0) if isinstance(data.get("total"), dict) else data.get("total", 0)
            hits = data.get("hits", [])
            if total == 0 or not hits:
                bot.send_message(chat_id=chat_id, text=f"No results for: {query}")
                return
            
            sample_hits = random.sample(hits, min(10, len(hits)))

            for h in sample_hits:
                text = f"File: {h.get('path')}\nLine {h.get('lineno')}: {h.get('line')}"
                bot.send_message(chat_id=chat_id, text=text)
            bot.send_message(chat_id=chat_id, text=f"Total matches: {total}")
        else:
            bot.send_message(chat_id=chat_id, text=f"Search error: {r.status_code}")
    except Exception as e:
        bot.send_message(chat_id=chat_id, text=f"Error during search: {e}")

def harvest_command(update: Update, context: CallbackContext):
    try:
        # Nội dung tin nhắn sau /harvest
        args_text = " ".join(context.args)

        # Tách domain và các tham số
        domain = None
        sources = ["brave,duckduckgo"]
        limit = 10

        parts = args_text.split()
        for i, part in enumerate(parts):
            if part.startswith("-s"):
                if i + 1 < len(parts):
                    sources = parts[i + 1]
            elif part.startswith("-l"):
                if i + 1 < len(parts):
                    limit = int(parts[i + 1])
            else:
                # Nếu chưa có domain thì lấy
                if domain is None and not part.startswith("-"):
                    domain = part

        if not domain:
            update.message.reply_text("❌ Bạn phải nhập domain.\nVí dụ: `/harvest example.com -s google -l 5`", parse_mode="Markdown")
            return

        # Gọi API
        params = {
            "domain": domain,
            "source": sources,
            "limit": limit
        }
        resp = requests.get(THEHARVESTER_API, params=params, timeout=60)

        if resp.status_code != 200:
            update.message.reply_text(f"⚠️ Lỗi API: {resp.status_code}")
            return

        data = resp.json()

        if not data:
            update.message.reply_text("🔍 Không tìm thấy kết quả.")
            return

        # Format kết quả (tùy chỉnh theo API)
        result_text = f"**Kết quả Harvest cho `{domain}`**\nNguồn: `{sources}`\nLimit: `{limit}`\n\n"
        result_text += "\n".join(data) if isinstance(data, list) else str(data)

        update.message.reply_text(result_text[:4000], parse_mode=None)

    except Exception as e:
        update.message.reply_text(f"❌ Lỗi: {str(e)}")

def show_sources(update: Update, context: CallbackContext):
    """Hiển thị danh sách các nguồn dữ liệu có sẵn."""
    sources = DEFAULT_SOURCES.split(',')
    formatted_sources = "\n".join(f"- {source.strip()}" for source in sources)
    update.message.reply_text(f"**Danh sách nguồn dữ liệu:**\n{formatted_sources}", parse_mode="Markdown")     

def tweetfeed(update: Update, context: CallbackContext):
    """Lấy danh sách IOCs từ TweetFeed API."""
    try:
        response = requests.get(TWEETFEED_API, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if not data:
                update.message.reply_text("Không có IOCs mới.")
                return

            formatted_iocs = []
            for item in data:
                date = item.get("date", "N/A")
                ioc_type = item.get("type", "N/A")
                value = item.get("value", "N/A")
                tags = " ".join(item.get("tags", [])) if item.get("tags") else ""
                tweet_url = item.get("tweet", "")
                user = item.get("user", "N/A")

                formatted_iocs.append(
                    f"📅 {date}\n👤 {user}\n🔍 {ioc_type}: `{value}`\n🏷 {tags}\n🔗 {tweet_url}"
                )

            update.message.reply_text(
                "**Danh sách IOCs hôm nay:**\n\n" + "\n\n".join(formatted_iocs),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        else:
            update.message.reply_text(f"Lỗi khi lấy dữ liệu: {response.status_code}")
    except Exception as e:
        update.message.reply_text(f"Lỗi: {str(e)}")
     
def social_search(update: Update, context: CallbackContext):
    query = ' '.join(context.args)
    if not query:
        update.message.reply_text("Usage: /social <query>")
        return

    update.message.reply_text(f"Searching social data for: {query} ...")

    try:
        r = requests.get(f"{SOCIAL_API}/social", params={"keyword": query, "limit": 20}, timeout=60)
        if r.status_code == 200:
            data = r.json()

            if not data:
                update.message.reply_text("No results found.")
                return

            formatted_results = []
            for item in data:
                source = item.get("source", "Unknown")
                keyword = item.get("keyword", "")
                content = item.get("content", "No Content")
                url = item.get("url", "No URL")
                ts = item.get("timestamp", None)

                # parse timestamp ISO → format dễ đọc
                if ts:
                    try:
                        ts_fmt = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        ts_fmt = ts
                else:
                    ts_fmt = "No Time"

                formatted_results.append(
                    f"📌 Source: {source}\n"
                    f"🔑 Keyword: {keyword}\n"
                    f"📝 {content[:200]}...\n"
                    f"🔗 [Open Link]({url})\n"
                    f"⏰ {ts_fmt}"
                )

            # Ghép thành message và chia nhỏ nếu quá dài
            output = "\n\n".join(formatted_results)
            for chunk in [output[i:i+3500] for i in range(0, len(output), 3500)]:
                update.message.reply_text(chunk, parse_mode="Markdown")

        else:
            update.message.reply_text(f"Search error: {r.status_code}")
    except Exception as e:
        update.message.reply_text(f"Error during search: {e}")


def show_help(update: Update, context: CallbackContext):
    """Hiển thị hướng dẫn sử dụng bot."""
    help_text = """
    **Hướng dẫn sử dụng bot:**

    /search <query> - Tìm kiếm thông tin từ database
    /ioc - Danh sách IOCs hàng ngày
    /harvest <domain> -s <source> -l <limit> - Thu thập thông tin từ các nguồn osint
    /source - Hiển thị danh sách các nguồn dữ liệu
    /help - Hiển thị hướng dẫn sử dụng
    """
    update.message.reply_text(help_text, parse_mode="Markdown")

'''
def outfile_cmd(update: Update, context):
    query = ' '.join(context.args)
    if not query:
        update.message.reply_text("Usage: /outfile <query>")
        return

    chat_id = update.message.chat_id
    update.message.reply_text(f"Generating file for: {query} ...")

    try:
        r = requests.get(f"{CRAWLER_API}/search", params={"q": query, "size": 10000, "outfile": "1"}, timeout=180)
        if r.status_code == 200:
            data = r.json()
            file_path = data.get("file_path")
            if not file_path or not os.path.isfile(file_path):
                update.message.reply_text("No file found or file missing.")
                return
            
            with open(file_path, "rb") as f:
                update.message.reply_document(document=InputFile(f, filename=f"search_{query}.txt"))

            # Chỉ gửi file 1 lần, không gọi lại API download
            with open(file_path, "rb") as f:
                update.message.reply_document(document=InputFile(f, filename=f"search_{query}.txt"))
        else:
            update.message.reply_text(f"Search error: {r.status_code}")
    except Exception as e:
        update.message.reply_text(f"Error during file generation: {e}")
'''

def run_flask():
    app.run(host="0.0.0.0", port=8000 ,threaded=True)

if __name__ == '__main__':
    # Chạy Flask trong thread phụ
    threading.Thread(target=run_flask, daemon=True).start()

    # Bot chạy ở main thread → không còn lỗi signal
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('search', search_cmd))
    #dp.add_handler(CommandHandler('outfile', outfile_cmd))
    dp.add_handler(CommandHandler("harvest", harvest_command))
    dp.add_handler(CommandHandler("source", show_sources))
    dp.add_handler(CommandHandler("help", show_help))
    dp.add_handler(CommandHandler("ioc", tweetfeed))
    dp.add_handler(CommandHandler("social", social_search))

    updater.start_polling()
    updater.idle()
