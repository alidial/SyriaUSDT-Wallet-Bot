import logging
import asyncio
import os
import threading
import sqlite3
from datetime import datetime

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
import aiohttp
from aiohttp import web

# 1. إعداد السجلات (Logs)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. البيانات الأساسية وإعدادات المتجر المتكاملة
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

# حالات المحادثة للبوت (Conversation States)
(
    SELECT_NETWORK, WAIT_AMOUNT, WAIT_RECEIPT, WAIT_SHAM_CASH,
    WAIT_USER_MESSAGE, WAIT_SET_BUY, WAIT_SET_SELL, WAIT_BROADCAST,
    WAIT_SERVICE_QUANTITY, WAIT_SEARCH_QUERY, WAIT_WALLET_DEPOSIT_AMT, 
    WAIT_WALLET_DEPOSIT_RE_C
) = range(12)

# 3. دالة حساب عمولة الأرباح بالليرة السورية (SYP) حسب طول الخانات تلقائياً
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
        logger.error(f"خطأ في حسبة السعر التلقائي: {e}")
        return original_price_str

# 4. تهيئة قاعدة البيانات المحلية للمتجر
def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            amount REAL,
            method TEXT,
            status TEXT DEFAULT 'PENDING',
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 5. واجهات تفاعل البوت والأزرار المنظمة لقسم المتجر والشحن
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    init_db()
    
    keyboard = [
        [InlineKeyboardButton("🛒 تصفح المتجر والخدمات", callback_data="browse_store")],
        [InlineKeyboardButton("🔍 البحث عن منتج", callback_data="search_product")],
        [InlineKeyboardButton("💰 شحن المحفظة (Shams / USDT)", callback_data="deposit_wallet")],
        [InlineKeyboardButton("📞 الدعم الفني المباشر", url=SUPPORT_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 أهلاً بك يا {user_name} في متجر سوريا المطور المتكامل والآمن!\n\n"
        "البوت يعمل الآن بأعلى كفاءة واستقرار على السيرفر المعزول.",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def browse_store(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # واجهة الـ 3 أعمدة للأقسام كما طلبت (العاب، شات، VPN)
    keyboard = [
        [
            InlineKeyboardButton("🎮 ألعاب", callback_data="cat_games"),
            InlineKeyboardButton("💬 شات", callback_data="cat_chat"),
            InlineKeyboardButton("🌐 VPN", callback_data="cat_vpn")
        ],
        [InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")]
    ]
    await query.edit_message_text(
        "🗂️ يرجى اختيار القسم المطلوب للتصفح الشامل:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "browse_store":
        await browse_store(update, context)
    elif query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("🛒 تصفح المتجر والخدمات", callback_data="browse_store")],
            [InlineKeyboardButton("💰 شحن المحفظة (Shams / USDT)", callback_data="deposit_wallet")]
        ]
        await query.edit_message_text("🎛️ القائمة الرئيسية للمتجر الحالية:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# 6. خادم ويب مدمج لتلبية طلبات Render الفورية
async def handle_render_web_request(request):
    return web.Response(text="Syria USDT Multi-Store Engine is fully operational without polling bugs!")

async def start_isolated_web_server():
    app = web.Application()
    app.router.add_get('/', handle_render_web_request)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🚀 خادم الويب الخدمي استقر على المنفذ: {port}")

# 7. دالة التشغيل الذكية والخارقة (تتجاوز خطأ بايثون 3.14 والـ Read-only)
async def main_async():
    logger.info("--- تفعيل نظام الإقلاع الآمن والمتكامل للمتجر ---")
    init_db()
    
    # تشغيل سيرفر الويب المساعد لـ Render
    await start_isolated_web_server()
    
    # بناء تطبيق البوت
    application = Application.builder().token(BOT_TOKEN).build()

    # إضافة معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons, pattern="^(browse_store|main_menu)$"))
    
    # تهيئة نوات البوت داخلياً بشكل يدوي وآمن
    await application.initialize()
    await application.start()
    
    logger.info("--- 🔥 تم تخطي حواجز run_polling والبدء بسحب الرسائل بنجاح! ---")
    
    # حلقة تكرارية مخصصة (Custom Loop) تسحب التحديثات يدوياً وتمنع انهيار البوت نهائياً
    offset = 0
    while True:
        try:
            updates = await application.bot.get_updates(offset=offset, timeout=20, allowed_updates=Update.ALL_TYPES)
            for update in updates:
                await application.process_update(update)
                offset = update.update_id + 1
        except asyncio.CancelledError:
            break
        except Exception as update_err:
            logger.error(f"تنبيه تحديث طبيعي: {update_err}")
            await asyncio.sleep(2)
        await asyncio.sleep(0.5)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("تم إيقاف النظام يدوياً.")

if __name__ == '__main__':
    main()
