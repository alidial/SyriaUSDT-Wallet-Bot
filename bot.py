import logging
import asyncio
import re
import os
import sqlite3
import math
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
import aiohttp
from aiohttp import web

# 1. إعداد السجلات (Logs)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. البيانات الأساسية للبوت والـ API والروابط
BOT_TOKEN = "8059151257:AAFngk1Wvv5wMxvJMywEAXqcx1q0X99HqM"
ADMIN_CHAT_ID = "920536751"
SUPPORT_LINK = "https://t.me/Syrusdt"

MOUSA_API_TOKEN = "C280gLYN12_xlghy548ztmGu60VUsbHuf6c_6Mwgvpbdvltov3ktxxmDZjHN"
MOUSA_API_BASE_URL = "https://mousa-card.com/api/v2"

MY_WALLETS = {
    "BEP20": "0x6567Dc3dAd882748121d65167977Bc0ad9F878d4",
    "TON": "UQBBXWRM9L4SlzlaFrwQdXmMqd6pNjS0Fha4Jba_pMTRnEFa",
    "TRC20 (TRX)": "0x6567Dc3dAd882748121d65167977Bc0ad9F878d4",
    "SHAM_CASH": "7a93267a0832F55F0b3Sabeadf28f896"
}

# حالات المحادثة المتعددة (Conversation States)
(
    SELECT_NETWORK, WAIT_AMOUNT, WAIT_RECEIPT, WAIT_SHAM_CASH,
    WAIT_USER_MESSAGE,
    WAIT_SET_BUY, WAIT_SET_SELL, WAIT_BROADCAST,
    WAIT_SET_START_HOUR, WAIT_SET_END_HOUR, WAIT_SERVICE_QUANTITY,
    WAIT_SEARCH_QUERY,
    WAIT_WALLET_DEPOSIT_AMT, WAIT_WALLET_DEPOSIT_RE_C
) = range(14)

# 3. دالة الحساب الديناميكي المحدثة حسب عدد خانات السعر
def calculate_custom_price(original_price_str):
    try:
        raw_price = float(original_price_str)
        price_int = int(raw_price)
        num_digits = len(str(price_int))
        
        if num_digits == 3:
            addition = 5
        elif num_digits == 4:
            addition = 10
        elif num_digits == 5:
            addition = 15
        elif num_digits == 6:
            addition = 20
        else:
            addition = 0
            
        return price_int + addition
    except Exception as e:
        logger.error(f"Error in price calculation: {e}")
        return original_price_str

# 4. الدوال البرمجية لإدارة تفاعلات البوت الأساسية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 أهلاً بك يا {user_name} في بوت سوريا USDT المطور!\n\n"
        "تم تشغيل السيرفر بنجاح ونظام المحافظ حى ومستقر الآن.",
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

async def handle_admin_global_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"Admin action triggered: {query.data}")

async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def receive_deposit_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def handle_unexpected_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("يرجى الضغط على /start لإعادة تشغيل البوت واستخدام القائمة.")

# 5. بناء تطبيق البوت لمرة واحدة فقط لمنع التصادم
application = Application.builder().token(BOT_TOKEN).build()

# 6. نظام خادم الويب المتوافق مع Render لضمان بقاء السيرفر حياً
async def handle_render_web_request(request):
    return web.Response(text="Bot is Running Live and Healthy!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_render_web_request)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server successfully started on port {port}")

def main():
    logger.info("... بدء تشغيل البوت المطور بنظام المحافظ ...")

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_search_query)],
            WAIT_WALLET_DEPOSIT_AMT: [CallbackQueryHandler(handle_buttons, pattern="^main_menu$")],
            WAIT_WALLET_DEPOSIT_RE_C: [
                CallbackQueryHandler(handle_buttons, pattern="^main_menu$"),
                MessageHandler(filters.PHOTO, receive_deposit_receipt)
            ]
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_admin_global_callback, pattern="^wlt_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message))

    # تشغيل سيرفر الويب والبوت معاً في نفس الـ Event Loop دون تعارض
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_web_server())
    
    # الإقلاع الآمن والمستقر للبوت
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
