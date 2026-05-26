import os
import logging
import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ============================================================
# ARIA BUSINESS BOT - بوت الأعمال الذكي
# Stack: python-telegram-bot + OpenRouter
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIG - من متغيرات البيئة
# ============================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
OPENROUTER_KEY   = os.environ.get("OPENROUTER_API_KEY", "")
MODEL            = os.environ.get("OPENROUTER_MODEL", "google/gemini-flash-1.5")
BOT_NAME         = "ARIA Business Bot"

# System prompt بالعربية
SYSTEM_PROMPT = """أنت ARIA، مساعد أعمال ذكي متخصص في مساعدة رواد الأعمال العرب.
تتحدث بالعربية الفصحى المبسطة أو الدارجة حسب المستخدم.
تساعد في: استراتيجية الأعمال، التسويق، الأتمتة، أدوات الذكاء الاصطناعي.
ردودك دائماً واضحة، عملية، ومباشرة."""

# ============================================================
# ذاكرة المحادثة (session-based)
# ============================================================
conversation_history: dict[int, list] = {}

def get_history(user_id: int) -> list:
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    return conversation_history[user_id]

def add_to_history(user_id: int, role: str, content: str):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    # احتفظ بآخر 10 رسائل فقط
    if len(history) > 10:
        conversation_history[user_id] = history[-10:]

# ============================================================
# استدعاء OpenRouter API
# ============================================================
def call_openrouter(user_id: int, user_message: str) -> str:
    add_to_history(user_id, "user", user_message)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://aria-business-bot.onrender.com",
        "X-Title": BOT_NAME,
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            *get_history(user_id),
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
        add_to_history(user_id, "assistant", reply)
        return reply

    except requests.exceptions.Timeout:
        return "⏱️ انتهت مهلة الاتصال، حاول مرة أخرى."
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return "⚠️ حدث خطأ تقني، حاول مرة أخرى."

# ============================================================
# Handlers
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    conversation_history[user_id] = []  # reset عند /start
    await update.message.reply_text(
        f"🤖 *{BOT_NAME}* جاهز!\n\n"
        "مرحباً بك — أنا ARIA، مساعدك الذكي للأعمال.\n"
        "كيف يمكنني مساعدتك اليوم؟",
        parse_mode="Markdown",
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🔄 تمت إعادة تعيين المحادثة.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    # مؤشر الكتابة
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    reply = call_openrouter(user_id, user_text)
    await update.message.reply_text(reply)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

# ============================================================
# MAIN
# ============================================================
def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("❌ TELEGRAM_TOKEN غير موجود في متغيرات البيئة")
    if not OPENROUTER_KEY:
        raise ValueError("❌ OPENROUTER_API_KEY غير موجود في متغيرات البيئة")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info(f"🚀 {BOT_NAME} يعمل الآن...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
