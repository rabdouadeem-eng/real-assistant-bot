import os, threading, requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

OPENROUTER_KEY = os.environ["OPENROUTER_KEY"]

SYSTEM = """أنت "مساعدك الحقيقي" — مساعد ذكي يتحدث العربية بشكل طبيعي.
تساعد الناس بصدق وبساطة. ردودك مختصرة ومفيدة."""

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    await update.message.chat.send_action("typing")
    res = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
        json={
            "model": "google/gemini-flash-1.5",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_msg}
            ]
        }
    ).json()
    reply = res["choices"][0]["message"]["content"]
    await update.message.reply_text(reply)

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass

def run_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), Health).serve_forever()

threading.Thread(target=run_server, daemon=True).start()
print("مساعدك الحقيقي شغال ✅")
app = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()
