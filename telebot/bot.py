import os
import requests
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler
import threading
from flask import Flask

# Load biến môi trường
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CRAWLER_API = os.getenv("CRAWLER_API", "http://crawler:5000")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set!")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

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
            for h in hits[:10]:
                text = f"File: {h.get('path')}\nLine {h.get('lineno')}: {h.get('line')}"
                bot.send_message(chat_id=chat_id, text=text)
            bot.send_message(chat_id=chat_id, text=f"Total matches: {total}")
        else:
            bot.send_message(chat_id=chat_id, text=f"Search error: {r.status_code}")
    except Exception as e:
        bot.send_message(chat_id=chat_id, text=f"Error during search: {e}")

def run_flask():
    app.run(host="0.0.0.0", port=8000)

if __name__ == '__main__':
    # Chạy Flask trong thread phụ
    threading.Thread(target=run_flask, daemon=True).start()

    # Bot chạy ở main thread → không còn lỗi signal
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('search', search_cmd))

    updater.start_polling()
    updater.idle()
