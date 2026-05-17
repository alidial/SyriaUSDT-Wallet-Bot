import logging
import asyncio
import os
import threading
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

WAIT_SEARCH_QUERY, WAIT_WALLET_DEPOSIT_AMT, WAIT_WALLET_DEPOSIT_RE_C = range(3)

# 3. الدوال الأساسية للتفاعل
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 أهلاً بك يا {user_name} في بوت سوريا USDT المطور!\n\n"
        "السيرفر يعمل الآن بأعلى استقرار وبنظام الخيوط المنفصلة.",
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

# 4. إعداد خادم الويب وجعله يعمل في الخيط المنفصل
async def handle_render_web_request(request):
    return web.Response(text="Bot Service is Active and Running!")

def start_web_server_thread():
    # إنشاء الـ Loop الخاص بالخيط المنفصل
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = web.Application()
    app.router.add_get('/', handle_render_web_request)
    
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    loop.run_until_complete(site.start())
    logger.info(f"🚀 Web server is isolated and online on port {port}")
    loop.run_forever()

# 5. الدالة الرئيسية للتشغيل المستقر
def main():
    logger.info("--- جاري إقلاع نظام البوت المعزول ---")
    
    # تشغيل سيرفر الويب في خلفية النظام (Thread منفصل) لتلبية متطلبات Render فوراً
    web_thread = threading.Thread(target=start_web_server_thread, daemon=True)
    web_thread.start()
    
    # بناء البوت بالطريقة الرسمية القياسية المستقرة
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

    # تشغيل البوت بسحب التحديثات المستقر والآمن تماماً
    logger.info("--- تم إطلاق البوت بنجاح تام وبدون أي تعارض ---")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
