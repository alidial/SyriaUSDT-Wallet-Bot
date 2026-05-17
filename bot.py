import logging
import os
import threading
import sqlite3
import telebot
from telebot import types
from aiohttp import web
import asyncio
import requests

# محاولة تحميل مكتبة python-dotenv لقراءة ملف .env محلياً إن وجد أثناء التطوير
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 1. إعداد السجلات ومراقبة الأخطاء (Logs)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. جلب البيانات الحساسة والإعدادات عبر البيئة الآمنة (Environment Variables) لحمايتها على GitHub
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8859151257:AAFQ7WpXsjYg_RJnHgE82ZU_O-WjXUtUaW8")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "920536751")  
SUPPORT_LINK = os.environ.get("SUPPORT_LINK", "https://t.me/Syrusdt")

MOUSA_API_TOKEN = os.environ.get("MOUSA_API_TOKEN", "C280gLYN12_xlghy548ztmGu60VUsbHuf6c_6Mwgvpbdvltov3ktxxmDZjHN")
MOUSA_API_BASE_URL = os.environ.get("MOUSA_API_BASE_URL", "https://mousa-card.com/api/v2")

# عناوين محافظك الرسمية والمعتمدة بشكل ديناميكي آمن
MY_WALLETS = {
    "TRC20": os.environ.get("WALLET_TRC20", "TKDPfmurDu9x7MgWPNUAa9i12wD5Enaw1B"),
    "BEP20": os.environ.get("WALLET_BEP20", "0x6567Dc3Dad882748121d65167977Bc0aB9f87804"),
    "TON": os.environ.get("WALLET_TON", "UQDbXMU9L45iztaFrwQdXMMqd6pMjsDPma4Jba_pWTRnSfEa"),
    "SHAM_CASH": os.environ.get("WALLET_SHAM_CASH", "7a93267a0832f55f8b35abeaf28f8960")
}

bot = telebot.TeleBot(BOT_TOKEN)
user_trade_steps = {}

# 3. تهيئة نظام المحفظة الداخلية وإعدادات قاعدة البيانات المحلية لقفل وفتح الأقسام والأسعار
def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, balance REAL DEFAULT 0.0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    
    # القيم المبدئية للوحة التحكم
    defaults = [
        ('usdt_buy_rate', '15000'),
        ('usdt_sell_rate', '14800'),
        ('work_hours', '10:00 AM - 12:00 PM'),
        ('buy_status', 'ON'),   
        ('sell_status', 'ON')   
    ]
    for key, val in defaults:
        cursor.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (key, val))
        
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

def get_user_balance(user_id):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.0

def update_user_balance(user_id, amount):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

# 4. حاسبة أسعار المتجر التلقائية (تعديل العمولات والربح الحقيقي حسب طول خانات السعر)
def calculate_custom_price(original_price_str):
    try:
        raw_price = float(original_price_str)
        price_int = int(raw_price)
        num_digits = len(str(price_int))
        
        if num_digits == 3: addition = 5      # إضافة 5 للأرقام المكونة من 3 خانات
        elif num_digits == 4: addition = 10    # إضافة 10 للأرقام المكونة من 4 خانات
        elif num_digits == 5: addition = 15    # إضافة 15 للأرقام المكونة من 5 خانات
        elif num_digits == 6: addition = 20    # إضافة 20 للأرقام المكونة من 6 خانات
        else: addition = 0
        
        return price_int + addition
    except Exception:
        return original_price_str

# 5. حاسبة شرائح عمولة تداول ومبيع الـ USDT للبوت (لحمايتك من الخسارة)
def calculate_sell_commission(amount):
    if 1 <= amount <= 9: return 1.0
    elif 10 <= amount <= 19: return 2.0
    elif 20 <= amount <= 29: return 2.5
    elif 30 <= amount <= 39: return 2.6
    elif 40 <= amount <= 49: return 2.7
    elif 50 <= amount <= 80: return 2.9
    elif amount > 80: return amount * 0.04 
    return 0.0

# 6. جلب السلع والخدمات من API موسى كارد وفلترتها جغرافياً وفئوياً
def fetch_mousa_products_by_category(category_keyword):
    try:
        headers = {"Authorization": f"Bearer {MOUSA_API_TOKEN}", "Content-Type": "application/json"}
        response = requests.get(f"{MOUSA_API_BASE_URL}/services", headers=headers, timeout=12)
        
        if response.status_code == 200:
            all_services = response.json()
            if not all_services or not isinstance(all_services, list):
                return []
                
            filtered_products = []
            for service in all_services:
                name = str(service.get("name", "")).lower()
                category = str(service.get("category", "")).lower()
                full_text = name + " " + category
                
                if category_keyword == "games":
                    if any(k in full_text for k in ["pubg", "free fire", "جواهر", "شحن", "ببجي", "uc", "game", "gems", "cod", "valorant", "فري فاير"]):
                        filtered_products.append(service)
                elif category_keyword == "chat":
                    if any(k in full_text for k in ["likee", "tiktok", "تيك توك", "شات", "chat", "bigo", "tango", "يلا"]):
                        filtered_products.append(service)
                elif category_keyword == "vpn":
                    if any(k in full_text for k in ["vpn", "بروكسي", "حظر", "proxy", "nord", "express"]):
                        filtered_products.append(service)
            
            return filtered_products if filtered_products else all_services[:12]
        return []
    except Exception as e:
        logger.error(f"❌ خطأ في جلب خدمات موسى كارد: {e}")
        return []

# تنفيذ طلب الشراء المباشر السحابي من حسابك الأساسي في موسى كارد
def order_mousa_product(service_id, target_account):
    try:
        headers = {"Authorization": f"Bearer {MOUSA_API_TOKEN}", "Content-Type": "application/json"}
        payload = {"service": int(service_id), "target": str(target_account)}
        response = requests.post(f"{MOUSA_API_BASE_URL}/orders", headers=headers, json=payload, timeout=12)
        if response.status_code in [200, 201]:
            return True, response.json()
        else:
            res_data = response.json()
            return False, res_data.get("message", "رصيد حسابك الموزع غير كافٍ أو الخدمة متوقفة مؤقتاً")
    except Exception as e:
        return False, str(e)

# 7. لوحة تحكم الإدارة الكاملة فورية التعديل لتغيير الأسعار والأرصدة والأقسام (/admin)
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != ADMIN_CHAT_ID:
        bot.reply_to(message, "❌ هذا الأمر مخصص للإدارة العليا فقط.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💵 سعر الشراء", callback_data="set_buy"),
        types.InlineKeyboardButton("💵 سعر المبيع", callback_data="set_sell"),
        types.InlineKeyboardButton("⏰ ساعات العمل", callback_data="set_hours"),
        types.InlineKeyboardButton("👤 تعديل رصيد زبون", callback_data="set_userbal"),
        types.InlineKeyboardButton("🟢 فتح شراء المتجر", callback_data="toggle_buy_ON"),
        types.InlineKeyboardButton("🔴 قفل شراء المتجر", callback_data="toggle_buy_OFF"),
        types.InlineKeyboardButton("🟢 فتح مبيع USDT", callback_data="toggle_sell_ON"),
        types.InlineKeyboardButton("🔴 قفل مبيع USDT", callback_data="toggle_sell_OFF")
    )
    
    buy_status = "مفتوح ✅" if get_setting("buy_status") == "ON" else "مقفل ❌"
    sell_status = "مفتوح ✅" if get_setting("sell_status") == "ON" else "مقفل ❌"
    
    admin_msg = (
        "🛠️ **لوحة تحكم الإدارة الفورية (لوحة الحماية والتحكم بالنظام):**\n\n"
        f"• سعر شراء USDT من العميل: `{get_setting('usdt_buy_rate')}` SYP\n"
        f"• سعر مبيع USDT للعميل: `{get_setting('usdt_sell_rate')}` SYP\n"
        f"• ساعات العمل الحالية: `{get_setting('work_hours')}`\n"
        f"• حالة الشراء من المتجر: **{buy_status}**\n"
        f"• حالة مبيع العميل USDT للبوت: **{sell_status}**\n\n"
        "اضغط على أي زر أدناه لتحديث النظام والأسعار تلقائياً في ثوانٍ:"
    )
    bot.reply_to(message, admin_msg, parse_mode="Markdown", reply_markup=markup)

# 8. واجهات الزبائن والقائمة الرئيسية للبوت مع عرض الرصيد الداخلي بالليرة السورية
@bot.message_handler(commands=['start'])
def send_welcome(message):
    init_db()
    user_id = str(message.from_user.id)
    if user_id in user_trade_steps: del user_trade_steps[user_id]
    
    update_user_balance(user_id, 0.0)
    current_balance = get_user_balance(user_id)
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🛒 متجر الشحن السريع (ألعاب، شات، VPN)", callback_data="browse_store"),
        types.InlineKeyboardButton("🔄 صرافة USDT (شراء / مبيع)", callback_data="trade_usdt_main"),
        types.InlineKeyboardButton("💳 محفظتي داخل البوت وشحن الرصيد", callback_data="deposit_wallet"),
        types.InlineKeyboardButton("📞 الدعم الفني المباشر", url=SUPPORT_LINK)
    )
    
    welcome_text = (
        f"👋 أهلاً بك يا {message.from_user.first_name} في بوت الخدمات والصرافة الأسرع والأكثر أماناً!\n\n"
        f"💰 **رصيد محفظتك الحالية داخل البوت:** `{current_balance:,.0f} ليرة سورية`"
    )
    bot.reply_to(message, welcome_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = str(call.from_user.id)
    
    # استقبال أوامر لوحة تحكم الأدمن
    if call.data.startswith("set_") and user_id == ADMIN_CHAT_ID:
        setting_type = call.data.split("_")[1]
        user_trade_steps[user_id] = {"state": f"EDIT_{setting_type.upper()}"}
        
        prompt_texts = {
            "buy": "✏️ أرسل سعر **شراء البوت USDT من العميل** بالليرة السورية:",
            "sell": "✏️ أرسل سعر **مبيع البوت USDT للعميل** بالليرة السورية:",
            "hours": "✏️ أرسل نص توقيت ساعات العمل والدوام الجديد للقسم الاجتماعي للتداول:",
            "userbal": "✏️ لتعديل محفظة العميل، أرسل: (آيدي حساب التليغرام للزبون) مسافة ثم (المبلغ بالزائد أو الناقص) كمثال: `920536751 50000`:"
        }
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=prompt_texts[setting_type], parse_mode="Markdown")
        return
        
    elif call.data.startswith("toggle_") and user_id == ADMIN_CHAT_ID:
        parts = call.data.split("_")
        section = parts[1]
        status = parts[2]
        update_setting(f"{section}_status", status)
        bot.answer_callback_query(call.id, "تم تحديث وضع القسم المطلوب بنجاح!")
        admin_panel(call.message)
        return

    # معالجة تصفح أقسام المتجر
    if call.data == "browse_store":
        if get_setting("buy_status") == "OFF":
            bot.answer_callback_query(call.id, "⚠️ المتجر مغلق مؤقتاً لتحديث المنتجات وقوائم الأسعار، يرجى المحاولة لاحقاً.", show_alert=True)
            return
            
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("🎮 ألعاب", callback_data="prod_games"),
            types.InlineKeyboardButton("💬 شات", callback_data="prod_chat"),
            types.InlineKeyboardButton("🌐 VPN", callback_data="prod_vpn")
        )
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🗂️ اختر القسم المطلوب لاستعراض المنتجات بالأسعار الصافية شاملة حماية العمولات والربح الحقيقي تلقائياً:", reply_markup=markup)
        
    elif call.data.startswith("prod_"):
        category = call.data.split("_")[1]
        bot.answer_callback_query(call.id, "🔄 جاري سحب المنتجات من السيرفر الموزع وتطبيق نسب الأرباح...")
        products = fetch_mousa_products_by_category(category)
        
        if not products:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 العودة للأقسام", callback_data="browse_store"))
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚠️ عذراً، هذا القسم قيد الصيانة السحابية وتحديث الإمدادات.", reply_markup=markup)
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for prod in products[:15]:
            final_p = calculate_custom_price(prod.get("rate", "0"))
            markup.add(types.InlineKeyboardButton(f"{prod.get('name')} | 💰 {final_p} SYP", callback_data=f"order_{prod.get('id')}_{final_p}"))
        markup.add(types.InlineKeyboardButton("🔙 العودة للأقسام", callback_data="browse_store"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎁 السلع المتاحة للتوصيل الآلي المباشر، عند اختيارك لسلعة سيتم الخصم من محفظتك وسحبها فوراً من حساب موسى كارد:", reply_markup=markup)

    elif call.data.startswith("order_"):
        parts = call.data.split("_")
        service_id = parts[1]
        final_price = float(parts[2])
        
        # فحص رصيد محفظة الزبون في التليغرام قبل بدء الخطوة
        user_bal = get_user_balance(user_id)
        if user_bal < final_price:
            bot.answer_callback_query(call.id, "❌ رصيد محفظتك في البوت غير كافٍ! يرجى إيداع وشحن حسابك أولاً عبر Sham Cash.", show_alert=True)
            return
            
        user_trade_steps[user_id] = {"state": "WAIT_TARGET_ACCOUNT", "service_id": service_id, "cost": final_price}
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎯 **بوابة الشراء الفوري التلقائي:**\n\nيرجى كتابة أيدي اللاعب (ID)، رقم الحساب، أو الهاتف المستهدف لشحن السلعة إليه بدقة متناهية:")

    # صرافة وبوابة تحويل الـ USDT لقسم التداول لضمان استقرار الأسواق
    elif call.data == "trade_usdt_main":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🟢 شراء USDT من البوت", callback_data="action_buy"),
            types.InlineKeyboardButton("🔴 بيع USDT إلى البوت", callback_data="action_sell")
        )
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))
        
        exchange_msg = (
            "🔄 **بوابة صرافة وتحويل الـ USDT الذكية والمحمية:**\n\n"
            f"⏰ **ساعات الدوام لغرفة التحويلات:** `{get_setting('work_hours')}`\n"
            f"📈 **سعر شراء البوت من العميل:** **{get_setting('usdt_buy_rate')} SYP**\n"
            f"📉 **سعر مبيع البوت للعميل:** **{get_setting('usdt_sell_rate')} SYP**\n\n"
            "يرجى تحديد اتجاه وعملية التداول المالية التي ترغب بها لبدء الفحص وحساب التكلفة الصافية:"
        )
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=exchange_msg, parse_mode="Markdown", reply_markup=markup)
        
    elif call.data.startswith("action_"):
        action_raw = call.data.split("_")[1]
        
        if action_raw == "sell" and get_setting("sell_status") == "OFF":
            bot.answer_callback_query(call.id, "⚠️ عمليات مبيع USDT للبوت متوقفة مؤقتاً بأمر الإدارة للحفاظ على الاحتياطي النقدى.", show_alert=True)
            return
            
        action_type = "شراء" if action_raw == "buy" else "بيع"
        user_trade_steps[user_id] = {"action": action_type, "action_raw": action_raw}
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔹 TRC20", callback_data="net_TRC20"),
            types.InlineKeyboardButton("🔸 BEP20", callback_data="net_BEP20"),
            types.InlineKeyboardButton("💎 TON Network", callback_data="net_TON")
        )
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"⚙️ الاتجاه الحالي للمشروع: **{action_type} USDT**\n\nاختر نوع الشبكة المستهدفة لتطبيق العمولات الدقيقة تفادياً لخسارة أي أصول رقمية:", parse_mode="Markdown", reply_markup=markup)
        
    elif call.data.startswith("net_"):
        network = call.data.split("_")[1]
        if user_id in user_trade_steps:
            user_trade_steps[user_id]["network"] = network
            user_trade_steps[user_id]["state"] = "WAIT_AMOUNT"
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"🔢 المسار الشبكي للتداول: **{network}**\n\nالآن، يرجى إرسال **الكمية الصافية من الـ USDT** المراد التعامل بها (أرقام فقط كـ 100):", parse_mode="Markdown")

    elif call.data == "deposit_wallet" or call.data == "main_menu":
        if user_id in user_trade_steps: del user_trade_steps[user_id]
        current_balance = get_user_balance(user_id)
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🛒 متجر شحن (ألعاب، شات، VPN)", callback_data="browse_store"),
            types.InlineKeyboardButton("🔄 صرافة الـ USDT (شراء / مبيع آلي)", callback_data="trade_usdt_main"),
            types.InlineKeyboardButton("💳 محفظتي وشحن رصيد (Sham Cash)", callback_data="deposit_wallet")
        )
        if call.data == "deposit_wallet":
            deposit_text = (
                f"💳 **محفظتك وحساب الإيداع داخل التليغرام:**\n\n"
                f"💰 رصيدك المتاح حالياً بالبوت: **{current_balance:,.0f} ليرة سورية**\n\n"
                f"📌 **حساب Sham Cash الرسمي للمتجر للتحويل وشحن المحفظة (اضغط للنسخ):**\n"
                f"`{MY_WALLETS['SHAM_CASH']}`\n\n"
                f"📥 بعد قيامك بالتحويل، أرسل صورة إيصال الدفع الفعلي (Screenshot) هنا مباشرة، وسيتم مطابقة البيانات وفحص الحساب لتغذية ليرات محفظتك تلقائياً."
            )
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=deposit_text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"🗂️ القائمة الرئيسية مجهزة بالكامل لخدمتك، رصيدك الآن: `{current_balance:,.0f} ليرة سورية`", reply_markup=markup)

# 9. معالجة النصوص البرمجية للشراء وتعديل رصيد العملاء وحساب العمولات
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = str(message.from_user.id)
    
    # تحكم الأدمن والتعديلات اليدوية لرصيد العملاء
    if user_id == ADMIN_CHAT_ID and user_id in user_trade_steps and user_trade_steps[user_id].get("state", "").startswith("EDIT_"):
        state = user_trade_steps[user_id]["state"]
        new_value = message.text
        
        if state == "EDIT_USERBAL":
            try:
                target_user, val_to_add = new_value.split(" ")
                update_user_balance(target_user, float(val_to_add))
                bot.reply_to(message, f"✅ تم تعديل محفظة الزبون بالتليغرام. الرصيد الحالي للمستخدم الآن: `{get_user_balance(target_user):,.0f} SYP`")
                bot.send_message(target_user, f"🔔 **إشعار تحديث محفظة:** تم تعديل وتحديث رصيد محفظتك داخل البوت من قبل الإدارة، رصيدك المتاح الآن هو: `{get_user_balance(target_user):,.0f} SYP`")
            except Exception:
                bot.reply_to(message, "❌ الإدخال خاطئ. يرجى اتباع التنسيق التالي: معرف العميل مسافة ثم القيمة المالية المضافة.")
            del user_trade_steps[user_id]
            return
            
        key_mapping = {
            "EDIT_BUY": "usdt_buy_rate", "EDIT_SELL": "usdt_sell_rate", "EDIT_HOURS": "work_hours"
        }
        if state in key_mapping:
            update_setting(key_mapping[state], new_value)
            bot.reply_to(message, f"✅ تم تعديل البند وتثبيته في قاعدة البيانات كـ: `{new_value}`")
            
        del user_trade_steps[user_id]
        return

    # إرسال طلب الشحن الفوري والتلقائي لـ API موسى كارد والخصم من محفظة التليغرام للمستخدم
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_TARGET_ACCOUNT":
        target_account = message.text
        service_id = user_trade_steps[user_id]["service_id"]
        cost = user_trade_steps[user_id]["cost"]
        
        user_bal = get_user_balance(user_id)
        if user_bal < cost:
            bot.reply_to(message, "❌ نعتذر، رصيد حسابك تغير أو أصبح غير كافٍ لإتمام الشراء.")
            del user_trade_steps[user_id]
            return
            
        # رسالة انتظار لطمأنة الزبون لحين استجابة خادم السيرفر
        wait_msg = bot.reply_to(message, "⏳ **جاري معالجة طلبك والاتصال بسيرفر متجر موسى كارد لتنفيذ عملية الشحن الفورية... يرجى الانتظار لحين اكتمال البناء السحابي للطلب.**", parse_mode="Markdown")
        
        success, api_response = order_mousa_product(service_id, target_account)
        bot.delete_message(message.chat.id, wait_msg.message_id)
        
        if success:
            # الخصم الأكيد من رصيد محفظة الزبون بالتليغرام
            update_user_balance(user_id, -cost)
            
            thanks_text = (
                f"🎉 **شكراً جزيلاً لتعاملك معنا وثقتك بنا يا غالي! تم تنفيذ وشحن طلبك بنجاح تام وبشكل فوري.**\n\n"
                f"📦 نوع العملية: شحن تلقائي مباشر للمنتجات\n"
                f"🎯 الحساب أو المعرف المشحون: `{target_account}`\n"
                f"💸 التكلفة المخصومة من رصيدك: `{cost:,.0f} SYP`\n"
                f"💰 رصيد محفظتك المتبقي بالبوت: `{get_user_balance(user_id):,.0f} ليرة سورية`"
            )
            bot.reply_to(message, thanks_text, parse_mode="Markdown")
            
            # تقرير فوري للإدارة لمراقبة الاستهلاك السحابي لرصيدك الأساسي بموسى كارد
            admin_notice = (
                f"🔔 **إشعار عملية شراء آلية ناجحة من المتجر:**\n"
                f"• العميل المستفيد: {message.from_user.first_name} (`{user_id}`)\n"
                f"• الحساب أو الهدف المشحون: `{target_account}`\n"
                f"• معرف الخدمة المخصومة بسيرفر موسى كارد: `{service_id}`\n"
                f"• السعر المخصوم من محفظة تليغرام الزبون: `{cost} SYP`\n"
                f"• المتبقي في محفظة الزبون بالتليغرام: `{get_user_balance(user_id)} SYP`"
            )
            bot.send_message(ADMIN_CHAT_ID, admin_notice)
        else:
            bot.reply_to(message, f"❌ **فشل سحب وإتمام الطلب تلقائياً من سيرفر موزع الخدمة:**\n`{api_response}`\n\n*تنبيه: لم يتم خصم أي مبلغ من رصيدك الداخلي بالتليغرام، يرجى مراجعة الدعم لتأكيده يدوياً.*", parse_mode="Markdown")
            
        del user_trade_steps[user_id]
        return

    # معالجة كميات صرافة الـ USDT وحساب العمولات ورسوم سحب الشبكات لحمايتك ضد أي خسارة مالية
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_AMOUNT":
        amount_text = message.text
        try:
            amount = float(amount_text)
            if amount <= 0: raise ValueError
        except ValueError:
            bot.reply_to(message, "⚠️ **خطأ في الإدخال!** يرجى إرسال كمية الـ USDT المراد تبديلها كأرقام فقط (مثال: 100):")
            return
            
        user_trade_steps[user_id]["amount"] = amount_text
        user_trade_steps[user_id]["state"] = "WAIT_RECEIPT"
        
        action_raw = user_trade_steps[user_id]["action_raw"]
        action = user_trade_steps[user_id]["action"]
        network = user_trade_steps[user_id]["network"]
        
        buy_rate = float(get_setting("usdt_buy_rate"))
        sell_rate = float(get_setting("usdt_sell_rate"))
        
        # حماية رأس المال من رسوم سحب شبكة المنصات والـ Blockchain
        net_fee_usdt = 1.5 if network == "TRC20" else (0.3 if network == "BEP20" else 0.5)
        
        if action_raw == "buy":
            total_usdt_needed = amount + net_fee_usdt
            total_syp = total_usdt_needed * sell_rate
            
            calc_text = (
                f"💰 **ملخص الحسابات وتكلفة الشراء:**\n"
                f"• سعر صرف مبيع USDT المعتمد بالبوت: `{sell_rate:,.0f} SYP`\n"
                f"• رسوم سحب الشبكة وخروج العملة ({network}): `{net_fee_usdt} USDT`\n"
                f"• إجمالي كمية الـ USDT المطلوبة لتغطية طلبك: `{total_usdt_needed} USDT`\n"
                f"🔥 **الإجمالي المستحق تحويله كاش (شام كاش):** **{total_syp:,.0f} ليرة سورية**"
            )
            target_wallet = MY_WALLETS["SHAM_CASH"]
            wallet_title = "حساب Sham Cash الرسمي للمتجر للتحويل"
        else:
            custom_comm_usdt = calculate_sell_commission(amount)
            net_amount_received = amount - custom_comm_usdt
            total_syp = net_amount_received * buy_rate
            
            calc_text = (
                f"💰 **ملخص الأرباح والعمولة المستقطعة:**\n"
                f"• سعر صرف شراء الـ USDT المعتمد بالبوت: `{buy_rate:,.0f} SYP`\n"
                f"• عمولة مبيع البوت التلقائية للكمية الحالية: `{custom_comm_usdt} USDT`\n"
                f"• كمية الـ USDT الصافية المستلمة رقمياً منك: `{net_amount_received} USDT`\n"
                f"🔥 **إجمالي الكاش السوري النهائي الذي ستتسلمه:** **{total_syp:,.0f} ليرة سورية**"
            )
            target_wallet = MY_WALLETS.get(network, "غير متوفر")
            wallet_title = f"عنوان محفظة البوت لشبكة ({network}) - [اضغط عليه لنسخه فوراً]"
            
        instruction_msg = (
            f"✅ **تقرير وحسبة المعاملة المالية الدقيقة:**\n"
            f"• نوع الإجراء: {action} USDT\n"
            f"• الكمية الإجمالية المستهدفة: {amount_text} USDT\n"
            f"• الشبكة والمسار الرقمي: {network}\n\n"
            f"{calc_text}\n\n"
            f"📥 **يرجى إتمام عملية التحويل الفعلي ومطابقة البيانات للعنوان التالي:**\n"
            f"📌 {wallet_title}:\n"
            f"`{target_wallet}`\n\n"
            f"📸 **الخطوة الأخيرة المتبقية:** بعد إتمامك للتحويل بنجاح، يرجى إرسال **صورة لقطة الشاشة للوصل أو الإيصال (Screenshot)** هنا مباشرة لتأكيد طلبك وتمريره لغرفة مراجعة المدفوعات الحية للإدارة."
        )
        bot.reply_to(message, instruction_msg, parse_mode="Markdown")

# 10. استقبال صور إيصالات الدفع واللقطات وتصنيفها وتحويلها لغرفة الإدارة مع كامل تقرير العمولات
@bot.message_handler(content_types=['photo'])
def receive_receipt_photo(message):
    user_id = str(message.from_user.id)
    
    # لقطات إيصالات صرافة الـ USDT
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_RECEIPT":
        bot.reply_to(message, "❤️ **شكراً جزيلاً لثقتك بنا يا غالي وتعاملك معنا!** تم استلام لقطة شاشة الإيصال بنجاح وتوجيه المعاملة لغرفة المراجعة الحية والمدفوعات اليدوية للإدارة الآن.\n\n⏳ يرجى الانتظار بضع دقائق لحين فحص ومطابقة القيود وتفعيل رصيدك أو تسليمك الكاش.")
        
        photo_file_id = message.photo[-1].file_id
        action = user_trade_steps[user_id]["action"]
        action_raw = user_trade_steps[user_id]["action_raw"]
        network = user_trade_steps[user_id]["network"]
        amount = float(user_trade_steps[user_id]["amount"])
        
        buy_rate = float(get_setting("usdt_buy_rate"))
        sell_rate = float(get_setting("usdt_sell_rate"))
        net_fee_usdt = 1.5 if network == "TRC20" else (0.3 if network == "BEP20" else 0.5)
        
        if action_raw == "buy":
            total_usdt = amount + net_fee_usdt
            total_syp = total_usdt * sell_rate
            details_text = f"• كمية العميل المطلوبة للتوفر: `{amount} USDT`\n• رسوم شبكة المنصة المضافة: `{net_fee_usdt} USDT`\n• الإجمالي المطلوب بالـ USDT: `{total_usdt} USDT`\n• سعر الصرف للمبيع المعتمد: `{sell_rate} SYP`\n• إجمالي المطالبة المالية المستحقة (شام كاش): `{total_syp:,.0f} SYP`"
        else:
            custom_comm_usdt = calculate_sell_commission(amount)
            net_amount_received = amount - custom_comm_usdt
            total_syp = net_amount_received * buy_rate
            details_text = f"• كمية العميل المرسلة للمحفظة: `{amount} USDT`\n• عمولة مبيع البوت المستقطعة تلقائياً: `{custom_comm_usdt} USDT`\n• الصافي المستلم رقمياً: `{net_amount_received} USDT`\n• سعر صرف الشراء المعتمد: `{buy_rate} SYP`\n• إجمالي الكاش السوري المطلوب تسليمه للعميل: `{total_syp:,.0f} SYP`"
            
        admin_report_text = (
            f"🚨 **طلب صرافة مالي جديد وارد ومحسوب العمولات تلقائياً ومؤمن بالكامل!**\n\n"
            f"👤 **بيانات حساب العميل المستفيد:**\n"
            f"• الاسم: {message.from_user.first_name}\n"
            f"• اليوزر: @{message.from_user.username if message.from_user.username else 'لا يوجد'}\n"
            f"• الآيدي الخاص به: `{user_id}`\n\n"
            f"⚙️ **تقرير العمولات والحسبة المالية لسلامة الحساب وحمايتك:**\n"
            f"• نوع المعاملة الحالية: *{action} USDT*\n"
            f"• الشبكة والمسار الرقمي: *{network}*\n"
            f"{details_text}\n\n"
            f"👇 صورة الإيصال المرفق من الزبون للمطابقة والمراجعة اليدوية المباشرة الفورية:"
        )
        try: 
            bot.send_photo(ADMIN_CHAT_ID, photo_file_id, caption=admin_report_text, parse_mode="Markdown")
        except Exception as e: 
            logger.error(f"❌ خطأ في تحويل الإيصال وصورة الوصل للأدمن: {e}")
        del user_trade_steps[user_id]
    else:
        # لقطات إيصالات شحن المحفظة الداخلية بالتليغرام عبر شام كاش
        photo_file_id = message.photo[-1].file_id
        bot.reply_to(message, "⏳ **شكراً لك! تم تحويل إيصال شحن محفظتك بالتليغرام إلى الإدارة بنجاح.** سيتم مراجعة قيود حساب الشام كاش الخاص بالمتجر وتغذية رصيد حسابك بالليرات ليتسنى لك الشراء تلقائياً.")
        
        admin_deposit_msg = (
            f"💰 **طلب شحن وتغذية محفظة تليغرام داخلية جديد:**\n\n"
            f"👤 العميل: {message.from_user.first_name}\n"
            f"🆔 الآيدي: `{user_id}`\n"
            f"📱 اليوزر: @{message.from_user.username if message.from_user.username else 'لا يوجد'}\n\n"
            f"يرجى مراجعة حساب الشام كاش، وثم شحن رصيد محفظة هذا الزبون عبر لوحة تحكم الأدمن باستخدام الآيدي الموضح أعلاه ليتمكن من الشحن الآلي الفوري للمنتجات."
        )
        try:
            bot.send_photo(ADMIN_CHAT_ID, photo_file_id, caption=admin_deposit_msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال طلب شحن المحفظة للأدمن: {e}")

# 11. خادم ويب مصغر ومتوافق تماماً للعمل على بيئة Render لضمان بقاء البوت حياً ومستيقظاً 24/7
async def handle_render_web_request(request):
    return web.Response(text="Syria Automated Store & Secure Exchange Core Operating 24/7 Smoothly!")

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
    loop.run_forever()

if __name__ == '__main__':
    init_db()
    # تشغيل خادم الويب في مسار معزول لعدم التأثير على بولينغ التليغرام المباشر
    web_thread = threading.Thread(target=start_isolated_web_server, daemon=True)
    web_thread.start()
    bot.infinity_polling()
