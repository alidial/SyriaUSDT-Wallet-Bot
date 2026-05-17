import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from aiohttp import web

# 1. إعداد السجلات (Logs)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. البيانات الأساسية
BOT_TOKEN = "8059151257:AAFngk1Wvv5wMxvJMywEAXqcx1q0X99HqM"
SUPPORT_LINK = "https://t.me/Syrusdt"

# حالات المحادثة
WAIT_SEARCH_QUERY, WAIT_WALLET_DEPOSIT_AMT, WAIT_WALLET_DEPOSIT_RE_C = range(3)

# 3. الدوال الأساسية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 أهلاً بك يا {user_name} في بوت سوريا USDT المطور!\n\n"
        "السيرفر يعمل الآن بنجاح واستقرار كامل.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("الدعم الفني", url=SUPPORT_LINK)]
        ])
    )
    return ConversationHandler.END

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("تم العودة للقائمة الرئيسية.")
    return ConversationHandler.END

async def handle_unexpected_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("يرجى إرسال /start لتشغيل البوت.")

# 4. سيرفر الويب الخاص بـ Render
async def handle_render_web_request(request):
    return web.Response(text="Bot is Live!")

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle_render_web_request)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server online on port {port}")

# 5. الدالة الرئيسية للتشغيل المستقر
def main():
    logger.info("--- جاري إقلاع نظام البوت المطور ---")
    
    # بناء التطبيق بالطريقة الرسمية الصحيحة
    application = Application.builder().token(BOT_TOKEN).build()

    # ربط الـ Handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message)],
            WAIT_WALLET_DEPOSIT_AMT: [CallbackQueryHandler(handle_buttons, pattern="^main_menu$")],
            WAIT_WALLET_DEPOSIT_RE_C: [CallbackQueryHandler(handle_buttons, pattern="^main_menu$")]
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False
    )
    
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message))

    # تشغيل سيرفر الويب في الخلفية بشكل آمن
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_web_server())
    except Exception as e:
        logger.error(f"Web server error: {e}")

    # تشغيل البوت بسحب التحديثات العادي المستقر
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
