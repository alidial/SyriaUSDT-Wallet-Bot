import logging
import os
import threading
import sqlite3
import telebot
from telebot import types
from aiohttp import web
import asyncio

# 1. إعداد السجلات (Logs)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. البيانات الأساسية وإعدادات المتجر
BOT_TOKEN = "8059151257:AAFngk1Wvv5wMxvJMywEAXqcx1q0X99HqM"
SUPPORT_LINK = "https://t.me/Syrusdt"

bot = telebot.TeleBot(BOT_TOKEN)

# 3. دالة حساب الأرباح الديناميكية تلقائياً بالليرة السورية
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
        logger.error(f"خطأ في حسبة السعر الديناميكي: {e}")
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
    conn.commit()
    conn.close()

# 5. دوال التفاعل مع المستخدم وعرض واجهة الـ 3 أعمدة
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
        f"👋 أهلاً بك يا {user_name} في متجر سوريا USDT المتكامل!\n\n"
        "البوت يعمل الآن على النظام المستقر الخالي من عيوب التحديثات.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "browse_store":
        # عرض الأقسام بـ 3 أعمدة متوازية تماماً كما طلبت
        markup = types.InlineKeyboardMarkup(row_width=3)
        btn_games = types.InlineKeyboardButton("🎮 ألعاب", callback_data="cat_games")
        btn_chat = types.InlineKeyboardButton("💬 شات", callback_data="cat_chat")
        btn_vpn = types.InlineKeyboardButton("🌐 VPN", callback_data="cat_vpn")
        btn_back = types.InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")
        
        markup.add(btn_games, btn_chat, btn_vpn)
        markup.add(btn_back)  # زر العودة في سطر منفصل أسفلهم
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🗂️ أقسام المتجر المتوفرة للتصفح التلقائي:",
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
            text="️ القائمة الرئيسية للمتجر الحالية:",
            reply_markup=markup
        )

# 6. خادم ويب مدمج لتلبية متطلبات نظام Render ومنع إغلاق السيرفر
async def handle_render_web_request(request):
    return web.Response(text="Mousa Card Multi-Store Engine is fully operational on telebot core!")

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

# 7. الإقلاع الرئيسي للملف
if __name__ == '__main__':
    logger.info("--- بدء إقلاع المحرك المستقر الجديد ---")
    init_db()
    
    # تشغيل خادم الويب في الخلفية بشكل معزول
    web_thread = threading.Thread(target=start_isolated_web_server, daemon=True)
    web_thread.start()
    
    # تشغيل سحب رسائل البوت بأمان
    logger.info("--- 🔥 تم إطلاق المتجر بنجاح وبأعلى درجات الاستقرار البيئي! ---")
    bot.infinity_polling()
