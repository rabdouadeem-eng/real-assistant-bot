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

# ========== قائمة النماذج المجانية المحدثة (مايو 2026) ==========
# ملاحظة: فقط النماذج التي تعمل حالياً
FREE_MODELS = [
    "openrouter/free",                              # ✅ يعمل - موجه ذكي
    "google/gemini-2.0-flash-001",                  # ✅ اسم جديد لنموذج Google
    "mistralai/mistral-small-3.1-24b-instruct:free", # ✅ نموذج Mistral
    "microsoft/phi-3.5-mini-instruct:free",          # ✅ نموذج Microsoft خفيف
    "qwen/qwen-2.5-7b-instruct:free"                # ✅ نسخة أصغر من Qwen (متاحة)
]

# ========== الذاكرة ==========
user_memory = {}
memory_lock = threading.Lock()

SYSTEM_PROMPT = """أنت "ARIA Business Bot" - مساعد أعمال ذكي بالعربية.
ردودك مختصرة ومفيدة ومهنية."""

def get_user_history(user_id):
    with memory_lock:
        if user_id not in user_memory:
            user_memory[user_id] = deque(maxlen=3)
        return list(user_memory[user_id])

def add_to_history(user_id, role, content):
    with memory_lock:
        if user_id not in user_memory:
            user_memory[user_id] = deque(maxlen=3)
        user_memory[user_id].append({"role": role, "content": content})

# ========== Cache بسيط ==========
cache = {}
cache_lock = threading.Lock()

def ask_openrouter_with_fallback(messages):
    """تجربة النماذج مرة واحدة لكل نموذج (بدون تكرار)"""
    
    # Cache
    cache_key = messages[-1]["content"][:100] if messages else ""
    with cache_lock:
        if cache_key in cache and (time.time() - cache[cache_key]["time"]) < 3600:
            logger.info(f"✅ رد من Cache")
            return cache[cache_key]["reply"]
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    
    for model in FREE_MODELS:
        logger.info(f"جاري تجربة النموذج: {model}")
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 256
        }
        
        try:
            start_time = time.time()
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    reply = data['choices'][0]['message']['content']
                    logger.info(f"✅ نجح النموذج: {model} في {elapsed:.1f} ثانية")
                    
                    with cache_lock:
                        cache[cache_key] = {"reply": reply, "time": time.time()}
                    return reply
                else:
                    logger.warning(f"{model}: استجابة غير متوقعة")
            else:
                logger.warning(f"{model}: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"{model}: انتهت المهلة")
        except Exception as e:
            logger.warning(f"{model}: {str(e)[:50]}")
    
    logger.error("جميع النماذج فشلت")
    return "⚠️ عذراً، جميع خدمات الذكاء الاصطناعي غير متاحة حالياً. حاول مجدداً بعد قليل."

# ========== معالج الرسائل ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    logger.info(f"مستخدم {user_id}: {user_message[:50]}")

    await update.message.chat.send_action(action="typing")

    add_to_history(user_id, "user", user_message)

    history = get_user_history(user_id)
    messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    reply = ask_openrouter_with_fallback(messages_for_api)

    if not reply.startswith("⚠️"):
        add_to_history(user_id, "assistant", reply)

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

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("✅ البوت شغال الآن...")
    app.run_polling()
