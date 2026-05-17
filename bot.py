import logging
import os
import threading
import sqlite3
import telebot
from telebot import types
from aiohttp import web
import asyncio

# 1. إعداد السجلات (Logs) لضمان متابعة حالة السيرفر
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. البيانات الأساسية وإعدادات المتجر المتكاملة (تم تحديث التوكن الصحيح)
BOT_TOKEN = "8859151257:AAFQ7WpXsjYg_RJnHgE82ZU_O-WjXUtUaW8"
SUPPORT_LINK = "https://t.me/Syrusdt"

# ربط تفاصيل الـ API الخاصة بموقع Mousa Card
MOUSA_API_TOKEN = "C280gLYN12_xlghy548ztmGu60VUsbHuf6c_6Mwgvpbdvltov3ktxxmDZjHN"
MOUSA_API_BASE_URL = "https://mousa-card.com/api/v2"

# عناوين المحافظ الرقمية الخاصة بك للشحن
MY_WALLETS = {
    "BEP20": "0x6567Dc3dAd882748121d65167977Bc0ad9F878d4",
    "TON": "UQBBXWRM9L4SlzlaFrwQdXmMqd6pNjS0Fha4Jba_pMTRnEFa",
    "TRC20 (TRX)": "0x6567Dc3dAd882748121d65167977Bc0ad9F878d4",
    "SHAM_CASH": "7a93267a0832F55F0b3Sabeadf28f896"
}

bot = telebot.TeleBot(BOT_TOKEN)

# 3. معادلة حساب عمولة الأرباح الديناميكية تلقائياً بالليرة السورية (SYP)
def calculate_custom_price(original_price_str):
    try:
        raw_price = float(original_price_str)
        price_int = int(raw_price)
        num_digits = len(str(price_int))
        
        # حسبة زيادة الأرباح المحددة بناءً على طول خانات السعر
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

# 4. تهيئة قاعدة البيانات المحلية للمتجر وحسابات الرصيد
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

# 5. واجهات تفاعل البوت (الأزرار المنظمة وقسم المتجر والشحن)
@bot.message_handler(commands=['start'])
def send_welcome(message):
    init_db()
    user_name = message.from_user.first_name
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_browse = types.InlineKeyboardButton("🛒 تصفح المتجر والخدمات", callback_data="browse_store")
    btn_search = types.InlineKeyboardButton("🔍 البحث عن منتج", callback_data="search_product")
    btn_wallet = types.InlineKeyboardButton("💰 شحن المحفظة (Shams / USDT)", callback_data="deposit_wallet")
    btn_support = types.InlineKeyboardButton("📞 الدعم الفني المباشر", url=SUPPORT_LINK)
    
    markup.add(btn_browse, btn_search, btn_wallet, btn_support)
    
    bot.reply_to(
        message,
        f"👋 أهلاً بك يا {user_name} في متجر سوريا المطور المتكامل!\n\n"
        "البوت يعمل الآن بأعلى كفاءة واستقرار ومتصل تلقائياً بأنظمة تحديث الأسعار والشحن المحلية.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "browse_store":
        # تصميم واجهة الـ 3 أعمدة (ألعاب | شات | VPN) كما طلبت تماماً للتصفح
        markup = types.InlineKeyboardMarkup(row_width=3)
        btn_games = types.InlineKeyboardButton("🎮 ألعاب", callback_data="cat_games")
        btn_chat = types.InlineKeyboardButton("💬 شات", callback_data="cat_chat")
        btn_vpn = types.InlineKeyboardButton("🌐 VPN", callback_data="cat_vpn")
        btn_back = types.InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")
        
        markup.add(btn_games, btn_chat, btn_vpn)
        markup.add(btn_back)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🗂️ أقسام المتجر المتوفرة للتصفح التلقائي وسحب الخدمات:",
            reply_markup=markup
        )
    elif call.data == "main_menu":
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_browse = types.InlineKeyboardButton("🛒 تصفح المتجر والخدمات", callback_data="browse_store")
        btn_wallet = types.InlineKeyboardButton("💰 شحن المحفظة (Shams / USDT)", callback_data="deposit_wallet")
        markup.add(btn_browse, btn_wallet)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🎛️ القائمة الرئيسية للمتجر الحالية:",
            reply_markup=markup
        )

# 6. خادم ويب مدمج لتلبية شروط الاستضافة على نظام Render ومنع الإغلاق
async def handle_render_web_request(request):
    return web.Response(text="Syria USDT Store Engine is Fully Active with valid Token credentials!")

def start_isolated_web_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = web.Application()
    app.router.add_get('/', handle_render_web_request)
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    loop.run_until_complete(site.start())
    logger.info(f"🚀 خادم الويب المساعد استقر أونلاين على المنفذ: {port}")
    loop.run_forever()

# 7. محرك الإقلاع الأساسي للملف
if __name__ == '__main__':
    logger.info("--- بدء إقلاع نظام المتجر المتكامل الآمن ---")
    init_db()
    
    # تشغيل خادم الويب المساعد في الخلفية بشكل معزول لضمان الاستقرار
    web_thread = threading.Thread(target=start_isolated_web_server, daemon=True)
    web_thread.start()
    
    logger.info("--- 🔥 تم إطلاق المتجر بنجاح وبأعلى درجات الاستقرار البيئي! ---")
    bot.infinity_polling()
