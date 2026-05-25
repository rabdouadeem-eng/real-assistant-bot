import os
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

app = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
print("مساعدك الحقيقي شغال ✅")
app.run_polling()
