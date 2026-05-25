import os, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from anthropic import Anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])

SYSTEM = """أنت "مساعدك الحقيقي" — مساعد ذكي يتحدث العربية بشكل طبيعي.
تساعد الناس بصدق وبساطة. ردودك مختصرة ومفيدة."""

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    await update.message.chat.send_action("typing")
    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_msg}]
    )
    await update.message.reply_text(res.content[0].text)

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
