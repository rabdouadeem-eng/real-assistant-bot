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
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# ========== إعداد التسجيل (logging) ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG if DEBUG else logging.INFO
)
logger = logging.getLogger(__name__)

# ========== الذاكرة البسيطة لكل مستخدم (آخر 5 رسائل + ردود) ==========
# هيكل التخزين: { user_id: deque(maxlen=10) }
# كل عنصر في deque هو قاموس {"role": "user" أو "assistant", "content": "النص"}
user_memory = {}
memory_lock = threading.Lock()  # قفل لضمان أمان التعددية

SYSTEM_PROMPT = """أنت "مساعدك الحقيقي" — مساعد ذكي يتحدث العربية بشكل طبيعي.
تساعد الناس بصدق وبساطة. ردودك مختصرة ومفيدة وتحترم المستخدم.
إذا سئل المستخدم عن اسمك، فقل أنك "مساعدك الحقيقي".
حافظ على لهجة ودودة ومحترمة."""

# ========== دوال مساعدة ==========
def get_user_history(user_id: int) -> list:
    """استرجاع تاريخ المحادثة للمستخدم (آخر 10 رسائل)."""
    with memory_lock:
        history = user_memory.get(user_id)
        if history is None:
            # إنشاء deque جديد إذا لم يكن موجوداً
            history = deque(maxlen=10)
            user_memory[user_id] = history
        return list(history)  # نسخة للقراءة فقط

def add_to_history(user_id: int, role: str, content: str):
    """إضافة رسالة جديدة إلى تاريخ المحادثة."""
    with memory_lock:
        if user_id not in user_memory:
            user_memory[user_id] = deque(maxlen=10)
        user_memory[user_id].append({"role": role, "content": content})

def clean_old_memories(max_users=1000):
    """حذف ذاكرة المستخدمين غير النشطين للحفاظ على الذاكرة (تنظيف دوري)."""
    # يمكن استدعاء هذه الوظيفة كل ساعة في خلفية، لكننا سنكتفي بالحذف عند تجاوز العدد
    with memory_lock:
        if len(user_memory) > max_users:
            # حذف أقدم 20% من المستخدمين (سيئ لكنه بسيط)
            to_remove = list(user_memory.keys())[:int(max_users * 0.2)]
            for uid in to_remove:
                del user_memory[uid]
            logger.info(f"Cleaned {len(to_remove)} inactive users from memory")

def call_openrouter_with_retry(messages, max_retries=2):
    """إرسال طلب إلى OpenRouter مع إعادة المحاولة التلقائية."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "google/gemini-flash-1.5",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024
    }
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()  # يرفع خطأ إذا كان الكود ليس 200
            data = response.json()
            # التحقق من وجود الرد
            if "choices" in data and len(data["choices"]) > 0:
                reply = data["choices"][0]["message"]["content"]
                return reply
            else:
                logger.error(f"OpenRouter response missing 'choices': {data}")
                raise ValueError("استجابة غير متوقعة من OpenRouter")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            if attempt == max_retries:
                return "⚠️ عذراً، حدثت مشكلة تقنية في الاتصال بالذكاء الاصطناعي. حاول مجدداً بعد قليل."
            time.sleep(2)  # انتظار قبل إعادة المحاولة
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return "⚠️ خطأ غير متوقع. يرجى المحاولة لاحقاً."
    return "⚠️ لم أتمكن من الحصول على رد. تحقق من اتصالك."

# ========== معالج الرسائل الرئيسي ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_msg = update.message.text
    logger.info(f"User {user_id}: {user_msg[:50]}")  # تسجيل أول 50 حرفاً

    # إظهار أن البوت يكتب
    await update.message.chat.send_action(action="typing")

    # 1. إضافة رسالة المستخدم إلى الذاكرة
    add_to_history(user_id, "user", user_msg)

    # 2. بناء قائمة الرسائل من الذاكرة مع إضافة النظام
    history = get_user_history(user_id)
    messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    # 3. استدعاء OpenRouter مع إعادة المحاولة
    reply = call_openrouter_with_retry(messages_for_api)

    # 4. إضافة رد البوت إلى الذاكرة
    if not reply.startswith("⚠️"):  # لا نحفظ رسائل الخطأ
        add_to_history(user_id, "assistant", reply)

    # 5. إرسال الرد للمستخدم (تقسيم الرسائل الطويلة)
    if len(reply) > 4096:
        for i in range(0, len(reply), 4096):
            await update.message.reply_text(reply[i:i+4096])
    else:
        await update.message.reply_text(reply)

    # 6. تنظيف الذاكرة كل 100 رسالة (تقريباً)
    if len(user_memory) % 100 == 0:
        threading.Thread(target=clean_old_memories, daemon=True).start()

# ========== خادم الصحة (health check) لبيئات الاستضافة ==========
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        # إخفاء logs خادم الصحة إذا لم يكن DEBUG
        if DEBUG:
            super().log_message(format, *args)

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"Health check server running on port {PORT}")
    server.serve_forever()

# ========== تشغيل البوت ==========
if __name__ == "__main__":
    # التحقق من وجود المفاتيح المطلوبة
    if not OPENROUTER_KEY or not TELEGRAM_TOKEN:
        raise ValueError("يرجى تعيين OPENROUTER_KEY و TELEGRAM_TOKEN في المتغيرات البيئية")

    # تشغيل خادم الصحة في خيط منفصل (لـ Render/Heroku)
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # إنشاء تطبيق البوت
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("✅ البوت شغال الآن...")
    app.run_polling()  # استخدام polling بدلاً من webhook (بسيط)
