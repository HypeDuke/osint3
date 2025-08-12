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



# Load biến môi trường
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CRAWLER_API = os.getenv("CRAWLER_API", "http://crawler:5000")
THEHARVESTER_API = os.getenv("THEHARVESTER_API", "http://theharvester_api:5100/query")

DEFAULT_SOURCES = (
    "api_endpoints,baidu,bevigil,bufferoverun,builtwith,brave,censys,"
    "certspotter,criminalip,crtsh,dehashed,dnsdumpster,duckduckgo,fullhunt,"
    "github-code,hackertarget,haveibeenpwned,hudsonrock,hunter,hunterhow,"
    "intelx,leaklookup,linkedin,linkedin_links,netcraft,netlas,omnisint,"
    "onyphe,otx,pentesttools,projectdiscovery,qwant,rapiddns,rocketreach,"
    "securityscorecard,securityTrails,shodan,subdomaincenter,"
    "subdomainfinderc99,sublist3r,threatcrowd,threatminer,tomba,urlscan,"
    "venacus,virustotal,whoisxml,yahoo,zoomeye,zoomeyeapi"
)
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)


MAX_MSG_LENGTH = 3500  # Telegram giới hạn độ dài tin nhắn

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
        sources = DEFAULT_SOURCES
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
            "sources": sources,
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

        update.message.reply_text(result_text[:4000], parse_mode="Markdown")

    except Exception as e:
        update.message.reply_text(f"❌ Lỗi: {str(e)}")

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


def run_flask():
    app.run(host="0.0.0.0", port=8000 ,threaded=True)

if __name__ == '__main__':
    # Chạy Flask trong thread phụ
    threading.Thread(target=run_flask, daemon=True).start()

    # Bot chạy ở main thread → không còn lỗi signal
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('search', search_cmd))
    dp.add_handler(CommandHandler('outfile', outfile_cmd))
    dp.add_handler(CommandHandler("harvest", harvest_command))

    updater.start_polling()
    updater.idle()
