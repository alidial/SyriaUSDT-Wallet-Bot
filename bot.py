import logging
import os
import threading
import sqlite3
import telebot
from telebot import types
from aiohttp import web
import asyncio
import requests

# 1. إعداد السجلات (Logs)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. إعداد التوكنات والآيدي المعتمد
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8859151257:AAF0SivQS_NiDcPaYiZFrt1p0Ep_T13lJTw")
ADMIN_CHAT_ID = "926536751"  
SUPPORT_LINK = "https://t.me/Syrusdt"

# توكن موسى كارد الكامل والجديد
MOUSA_API_TOKEN = "K6ZRGXAYGsw6WYJJFwJA91yci5dqTjg7b7sc8hEjLruWihH9uNUFokX0dW3PWtqX"
MOUSA_API_BASE_URL = "https://mousa-card.com/api/v2"

MY_WALLETS = {
    "TRC20": "TKDPfmurDu9x7MgWPNUAa9i12wD5Enaw1B",
    "BEP20": "0x6567Dc3Dad882748121d65167977Bc0aB9f87804",
    "TON": "UQDbXMU9L45iztaFrwQdXMMqd6pMjsDPma4Jba_pWTRnSfEa",
    "SHAM_CASH": "7a93267a0832f55f8b35abeaf28f8960"
}

bot = telebot.TeleBot(BOT_TOKEN)
user_trade_steps = {}

def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, balance REAL DEFAULT 0.0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('usdt_buy_rate', '15000')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('usdt_sell_rate', '14800')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('work_hours', '10:00 AM - 12:00 PM')")
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('bot_status', 'ON')")
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "0"

def update_setting(key, value):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
    conn.commit()
    conn.close()

# 4. الدالة المحدثة كلياً لجلب الخدمات وفك شفرة استجابة الـ API
def fetch_mousa_products_by_category(category_keyword):
    try:
        # استخدام صيغة طلب متوافقة مع الـ API (تعديل الهيدر ليطابق توثيق المتجر الرسمي)
        headers = {
            "Authorization": f"Bearer {MOUSA_API_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # طلب قائمة الخدمات
        response = requests.get(f"{MOUSA_API_BASE_URL}/services", headers=headers, timeout=15)
        logger.info(f"Mousa API Status Code: {response.status_code}")
        
        if response.status_code == 200:
            res_data = response.json()
            
            # معالجة استجابة الـ API إذا كانت مصفوفة مباشرة أو كائن يحتوي على مفتاح داخلي
            all_services = []
            if isinstance(res_data, list):
                all_services = res_data
            elif isinstance(res_data, dict):
                # فحص الكلمات المفتاحية الشهيرة التي يرجعها المتجر داخل قواميس البيانات
                if "services" in res_data: all_services = res_data["services"]
                elif "data" in res_data: all_services = res_data["data"]
                elif "result" in res_data: all_services = res_data["result"]
                else: all_services = list(res_data.values())[0] if res_data else []

            if not all_services or not isinstance(all_services, list):
                logger.warning("❌ لم يتم العثور على مصفوفة خدمات صالحة داخل الاستجابة.")
                return []
            
            filtered_products = []
            for service in all_services:
                if not isinstance(service, dict): continue
                
                # جلب الاسم والتصنيف والوصف لزيادة دقة البحث
                name = str(service.get("name", "")).lower()
                category = str(service.get("category", "")).lower()
                description = str(service.get("description", "")).lower()
                full_text = f"{name} {category} {description}"
                
                # تصفية المحتوى بناءً على الكلمات المفتاحية الشاملة (عربي وإنجليزي)
                if category_keyword == "games":
                    if any(k in full_text for k in ["pubg", "free fire", "جواهر", "شحن", "ببجي", "uc", "game", "gems", "cod", "valorant", "فري", "فاير", "coins", "كاش", "لودو", "ludo", "جواهر"]):
                        filtered_products.append(service)
                elif category_keyword == "chat":
                    if any(k in full_text for k in ["likee", "tiktok", "تيك", "توك", "شات", "chat", "bigo", "tango", "yalla", "يلا", "برنامج", "ماسنجر", "لايكي", "بيجو"]):
                        filtered_products.append(service)
                elif category_keyword == "vpn":
                    if any(k in full_text for k in ["vpn", "بروكسي", "proxy", "nord", "express", "حظر", "تطبيق", "شبكة"]):
                        filtered_products.append(service)
            
            # 🚨 خطة الطوارئ: إذا لم تطابق الفلترة أي عنصر، اعرض أول 20 خدمة خام ليعمل المتجر فوراً
            if not filtered_products and all_services:
                logger.info("⚠️ لم تطابق الفلترة أي منتج، يتم تشغيل خطة الطوارئ وعرض الخدمات الخام.")
                return all_services[:20]
                
            return filtered_products
        else:
            logger.error(f"❌ استجابة السيرفر خاطئة: {response.text}")
            return []
    except Exception as e:
        logger.error(f"❌ خطأ فني أثناء الاتصال بـ API موسى كارد: {e}")
        return []

# 5. لوحة تحكم الأدمن (/admin)
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != ADMIN_CHAT_ID:
        bot.reply_to(message, "❌ هذا الأمر مخصص حصرياً لمالك البوت.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💵 شراء USDT", callback_data="set_buy"),
        types.InlineKeyboardButton("💵 مبيع USDT", callback_data="set_sell"),
        types.InlineKeyboardButton("⏰ الساعات", callback_data="set_hours"),
        types.InlineKeyboardButton("🟢 تشغيل الصرافة", callback_data="status_ON"),
        types.InlineKeyboardButton("🔴 إيقاف الصرافة", callback_data="status_OFF")
    )
    current_status = "نشط ✅" if get_setting("bot_status") == "ON" else "متوقف مؤقتاً ❌"
    bot.reply_to(message, f"🛠️ **لوحة التحكم بالصرافة وحالة البوت:**\n\nوضع الصرافة الحالي: {current_status}", parse_mode="Markdown", reply_markup=markup)

# 6. القائمة الرئيسية
@bot.message_handler(commands=['start'])
def send_welcome(message):
    init_db()
    user_id = str(message.from_user.id)
    if user_id in user_trade_steps: del user_trade_steps[user_id]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🛒 تصفح المتجر (ألعاب وتطبيقات)", callback_data="browse_store"),
        types.InlineKeyboardButton("🔄 شراء ومبيع USDT / صرافة آلي", callback_data="trade_usdt_main"),
        types.InlineKeyboardButton("💰 شحن محفظة البوت (Sham Cash)", callback_data="deposit_wallet"),
        types.InlineKeyboardButton("📞 الدعم الفني المباشر", url=SUPPORT_LINK)
    )
    bot.reply_to(message, f"👋 أهلاً بك يا {message.from_user.first_name} في بوت الخدمات المطور سـوريا!", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = str(call.from_user.id)
    if call.data.startswith("set_") and user_id == ADMIN_CHAT_ID:
        setting_type = call.data.split("_")[1]
        user_trade_steps[user_id] = {"state": f"EDIT_{setting_type.upper()}"}
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"✏️ أرسل القيمة المحدثة والجديدة للبند المحدد حالياً:")
        return
    elif call.data.startswith("status_") and user_id == ADMIN_CHAT_ID:
        update_setting("bot_status", call.data.split("_")[1])
        admin_panel(call.message)
        return

    if call.data == "browse_store":
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("🎮 ألعاب", callback_data="prod_games"),
            types.InlineKeyboardButton("💬 شات", callback_data="prod_chat"),
            types.InlineKeyboardButton("🌐 VPN", callback_data="prod_vpn")
        )
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🗂️ يرجى اختيار القسم المراد تصفحه الآن:", reply_markup=markup)
    
    elif call.data.startswith("prod_"):
        category = call.data.split("_")[1]
        bot.answer_callback_query(call.id, "🔄 جاري الاتصال بالمتجر وسحب الخدمات الحية...")
        products = fetch_mousa_products_by_category(category)
        
        if not products:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 عودة للتصنيفات", callback_data="browse_store"))
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚠️ لم نتمكن من العثور على خدمات نشطة في حساب موسى كارد حالياً. تأكد من شحن حسابك في الموقع وتفعيل الخدمات هناك.", reply_markup=markup)
            return
            
        markup = types.InlineKeyboardMarkup(row_width=3)
        btn_list = []
        for prod in products[:18]:
            # مرونة في قراءة السعر لتجنب قراءة قيم صفرية
            raw_p = prod.get("rate") or prod.get("price") or prod.get("cost", "0")
            prod_name = prod.get("name", "خدمة غير مسماة")
            btn_list.append(types.InlineKeyboardButton(f"{prod_name} | {raw_p} SP", callback_data=f"sel_{prod.get('id')}_{raw_p}"))
            
        for i in range(0, len(btn_list), 3): 
            markup.add(*btn_list[i:i+3])
        markup.add(types.InlineKeyboardButton("🔙 عودة الأقسام", callback_data="browse_store"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎁 الخدمات المتاحة بالأسعار الخام الحقيقية من حسابك المباشر:", reply_markup=markup)
    
    elif call.data.startswith("sel_"):
        parts = call.data.split("_")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("✅ تأكيد الشراء وإرسال الطلب", callback_data=f"conf_{parts[1]}_{parts[2]}"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"🛍️ تأكيد طلب الشراء للخدمة رقم `{parts[1]}` بقيمة: **{parts[2]} ليرة سورية**", parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("conf_"):
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❤️ تم إرسال طلبك بنجاح للإدارة! سيقوم الدعم بمطابقة الحساب وتسليمك الكود فوراً.")
        try: bot.send_message(ADMIN_CHAT_ID, f"🛒 **طلب شراء جديد (بالسعر الخام):**\n• رقم الخدمة: `{call.data.split('_')[1]}`\n• السعر الأساسي: **{call.data.split('_')[2]} ليرة سورية**\n• حساب العميل: {user_id}")
        except Exception: pass

    elif call.data == "trade_usdt_main":
        if get_setting("bot_status") == "OFF":
            bot.answer_callback_query(call.id, "⚠️ قسم الصرافة متوقف حالياً")
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("🟢 شراء USDT", callback_data="action_buy"), types.InlineKeyboardButton("🔴 بيع USDT", callback_data="action_sell"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🔄 بوابة الصرافة وتحويل الـ USDT الأساسية في سوريا:", reply_markup=markup)
    elif call.data.startswith("action_"):
        user_trade_steps[user_id] = {"action_raw": call.data.split("_")[1]}
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(types.InlineKeyboardButton("TRC20", callback_data="net_TRC20"), types.InlineKeyboardButton("BEP20", callback_data="net_BEP20"), types.InlineKeyboardButton("TON", callback_data="net_TON"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚙️ حدد شبكة التحويل المالي المطلوبة:", reply_markup=markup)
    elif call.data.startswith("net_"):
        if user_id in user_trade_steps:
            user_trade_steps[user_id]["network"] = call.data.split("_")[1]
            user_trade_steps[user_id]["state"] = "WAIT_AMOUNT"
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🔢 أرسل كمية الـ USDT (أرقام فقط):")
    elif call.data == "deposit_wallet" or call.data == "main_menu":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"💰 **حساب شحن المتجر السوري (Sham Cash):**\n`{MY_WALLETS['SHAM_CASH']}`\n\nيرجى تحويل الرصيد ثم إرسال الصورة لتوثيق الحساب.")

# 7. الرسائل النصية
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = str(message.from_user.id)
    if user_id == ADMIN_CHAT_ID and user_id in user_trade_steps and str(user_trade_steps[user_id].get("state", "")).startswith("EDIT_"):
        state = user_trade_steps[user_id]["state"]
        key_mapping = {"EDIT_BUY": "usdt_buy_rate", "EDIT_SELL": "usdt_sell_rate", "EDIT_HOURS": "work_hours"}
        if state in key_mapping:
            update_setting(key_mapping[state], message.text)
            bot.reply_to(message, f"✅ تم تحديث السعر بنجاح.")
        del user_trade_steps[user_id]
        return

    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_AMOUNT":
        user_trade_steps[user_id]["amount"] = message.text
        user_trade_steps[user_id]["state"] = "WAIT_RECEIPT"
        net = user_trade_steps[user_id]["network"]
        w = MY_WALLETS.get(net if user_trade_steps[user_id]["action_raw"] != "buy" else "SHAM_CASH")
        bot.reply_to(message, f"📥 يرجى تحويل القيمة للعنوان التالي:\n`{w}`\n\n📸 بعد التحويل، أرسل لقطة الشاشة (Screenshot) هنا.")

# 8. صور الإيصالات
@bot.message_handler(content_types=['photo'])
def receive_receipt_photo(message):
    user_id = str(message.from_user.id)
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_RECEIPT":
        bot.reply_to(message, "❤️ تسلم، تم استقبال لقطة الشاشة وجاري مطابقتها من قبل الإدارة.")
        try: bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=f"🚨 **إشعار دفع جديد:**\n• العميل: `{user_id}`\n• المعاملة: {user_trade_steps[user_id]['action_raw'].upper()}\n• الكمية: `{user_trade_steps[user_id]['amount']}` USDT")
        except Exception: pass
        del user_trade_steps[user_id]

# 9. خادم الويب لـ Render
async def handle_render_web_request(request):
    return web.Response(text="Mousa Card API Fix Active!")

def start_isolated_web_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = web.Application()
    app.router.add_get('/', handle_render_web_request)
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 10000)))
    loop.run_until_complete(site.start())
    loop.run_forever()

if __name__ == '__main__':
    init_db()
    threading.Thread(target=start_isolated_web_server, daemon=True).start()
    bot.infinity_polling()
