import os
import threading
import requests
import time
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import deque
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ========== إعدادات البيئة ==========
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

# ========== إعداد التسجيل ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== الذاكرة البسيطة ==========
user_memory = {}
memory_lock = threading.Lock()

SYSTEM_PROMPT = """أنت "ARIA Business Bot" - مساعد أعمال ذكي بالعربية.
ردودك مختصرة ومفيدة ومهنية. تساعد في حل المشكلات والإجابة عن الأسئلة."""

def get_user_history(user_id):
    with memory_lock:
        if user_id not in user_memory:
            user_memory[user_id] = deque(maxlen=6)
        return list(user_memory[user_id])

def add_to_history(user_id, role, content):
    with memory_lock:
        if user_id not in user_memory:
            user_memory[user_id] = deque(maxlen=6)
        user_memory[user_id].append({"role": role, "content": content})

# ========== الاتصال بـ OpenRouter ==========
def ask_openrouter(messages):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    # استخدم نموذجًا مجانيًا وموثوقًا
    payload = {
        "model": "nousresearch/hermes-3-llama-3.1-405b:free",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 800
    }
    for attempt in range(2):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=40)
            if response.status_code == 200:
                data = response.json()
                reply = data['choices'][0]['message']['content']
                return reply
            else:
                logger.error(f"HTTP {response.status_code}: {response.text[:200]}")
        except Exception as e:
            logger.error(f"محاولة {attempt+1} فشلت: {e}")
            time.sleep(2)
    return "⚠️ عذراً، حدثت مشكلة في الاتصال بالذكاء الاصطناعي. حاول مجدداً بعد قليل."

# ========== معالج الرسائل ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    logger.info(f"مستخدم {user_id}: {user_message[:50]}")

    # إظهار أن البوت يكتب
    await update.message.chat.send_action(action="typing")

    # حفظ رسالة المستخدم
    add_to_history(user_id, "user", user_message)

    # جلب التاريخ وتحضير الرسائل
    history = get_user_history(user_id)
    messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    # الحصول على الرد
    reply = ask_openrouter(messages_for_api)

    # حفظ رد البوت إذا لم يكن خطأ
    if not reply.startswith("⚠️"):
        add_to_history(user_id, "assistant", reply)

    # إرسال الرد (تقسيم الطويل)
    if len(reply) > 4096:
        for i in range(0, len(reply), 4096):
            await update.message.reply_text(reply[i:i+4096])
    else:
        await update.message.reply_text(reply)

# ========== خادم الصحة ==========
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"خادم الصحة يعمل على المنفذ {PORT}")
    server.serve_forever()

# ========== التشغيل ==========
if __name__ == "__main__":
    if not OPENROUTER_KEY:
        raise ValueError("يرجى تعيين OPENROUTER_KEY في المتغيرات البيئية")
    if not TELEGRAM_TOKEN:
        raise ValueError("يرجى تعيين TELEGRAM_TOKEN في المتغيرات البيئية")

    # تشغيل خادم الصحة في خيط منفصل
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # إنشاء وتشغيل البوت
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("✅ البوت شغال الآن...")
    app.run_polling()
