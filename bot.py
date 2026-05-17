import logging
import os
import threading
import sqlite3
import telebot
from telebot import types
from aiohttp import web
import asyncio
import requests

# 1. إعداد السجلات (Logs) لمراقبة الاتصال
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. البيانات الأساسية والإعدادات الثابتة (التوكن الجديد مدمج بشكل مباشر وصارم)
# التوكن الجديد مدمج هنا كقيمة افتراضية ثابتة لمنع المنصة من استخدام التوكن القديم
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8859151257:AAGhwQrrtdyC1ihQ5cn2iaBshIcnemEM3WA").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "920536751").strip()
SUPPORT_LINK = os.environ.get("SUPPORT_LINK", "https://t.me/Syrusdt").strip()

MOUSA_API_TOKEN = os.environ.get("MOUSA_API_TOKEN", "C280gLYN12_xlghy548ztmGu60VUsbHuf6c_6Mwgvpbdvltov3ktxxmDZjHN").strip()
MOUSA_API_BASE_URL = os.environ.get("MOUSA_API_BASE_URL", "https://mousa-card.com/api/v2").strip()

# عناوين المحافظ الرسمية والمعتمدة بنسبة 100%
MY_WALLETS = {
    "TRC20": os.environ.get("WALLET_TRC20", "TKDPfmurDu9x7MgWPNUAa9i12wD5Enaw1B").strip(),
    "BEP20": os.environ.get("WALLET_BEP20", "0x6567Dc3Dad882748121d65167977Bc0aB9f87804").strip(),
    "TON": os.environ.get("WALLET_TON", "UQDbXMU9L45iztaFrwQdXMMqd6pMjsDPma4Jba_pWTRnSfEa").strip(),
    "SHAM_CASH": os.environ.get("WALLET_SHAM_CASH", "7a93267a0832f55f8b35abeaf28f8960").strip()
}

bot = telebot.TeleBot(BOT_TOKEN)
user_trade_steps = {}

# 3. تهيئة قاعدة البيانات المحلية للأقسام والأسعار
def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, balance REAL DEFAULT 0.0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('usdt_buy_rate', '15000')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('usdt_sell_rate', '14800')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('my_commission', '200')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('network_fee_trc20', '1.5')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('network_fee_bep20', '0.3')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('network_fee_ton', '0.5')") 
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

# 4. حاسبة الأرباح التلقائية للمتجر (حسب طول خانات الرقم لضمان الربح الحقيقي)
def calculate_custom_price(original_price_str):
    try:
        raw_price = float(original_price_str)
        price_int = int(raw_price)
        num_digits = len(str(price_int))
        
        if num_digits == 3: addition = 5
        elif num_digits == 4: addition = 10
        elif num_digits == 5: addition = 15
        elif num_digits == 6: addition = 20
        else: addition = 0
        
        return price_int + addition
    except Exception:
        return original_price_str

# 5. جلب خدمات Mousa Card مع تحسين الفلترة الذكية والخيار الاحتياطي السحابي
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
            
            if not filtered_products and all_services:
                return all_services[:10]
                
            return filtered_products
        return []
    except Exception as e:
        logger.error(f"❌ خطأ أثناء الاتصال بـ Mousa Card API: {e}")
        return []

# 6. لوحة تحكم الأدمن والتحكم الفوري بالأسعار والعمولات والتشغيل (/admin)
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != ADMIN_CHAT_ID:
        bot.reply_to(message, "❌ نعتذر، هذا الأمر مخصص فقط لمالك البوت الأصلي.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💵 سعر الشراء الخام", callback_data="set_buy"),
        types.InlineKeyboardButton("💵 سعر Mبيع الخام", callback_data="set_sell"),
        types.InlineKeyboardButton("💰 عمولتك بالليرة", callback_data="set_mycomm"),
        types.InlineKeyboardButton("🌐 عمولة منصة TRC20", callback_data="set_feetrc"),
        types.InlineKeyboardButton("🌐 عمولة منصة BEP20", callback_data="set_feebep"),
        types.InlineKeyboardButton("🌐 عمولة منصة TON", callback_data="set_feeton"),
        types.InlineKeyboardButton("⏰ أوقات العمل", callback_data="set_hours"),
        types.InlineKeyboardButton("🟢 تشغيل الصرافة", callback_data="status_ON"),
        types.InlineKeyboardButton("🔴 إيقاف الصرافة", callback_data="status_OFF")
    )
    
    current_status = "نشط ✅" if get_setting("bot_status") == "ON" else "متوقف مؤقتاً ❌"
    admin_msg = (
        "🛠️ **لوحة التحكم المباشرة للإدارة وحساب العمولات:**\n\n"
        f"• سعر الشراء الخام: `{get_setting('usdt_buy_rate')}` SYP\n"
        f"• سعر المبيع الخام: `{get_setting('usdt_sell_rate')}` SYP\n"
        f"• عمولتك الشخصية المضافة: `{get_setting('my_commission')}` SYP / لكل 1 USDT\n"
        f"• عمولة سحب المنصة لـ TRC20: `{get_setting('network_fee_trc20')}` USDT\n"
        f"• عمولة سحب المنصة لـ BEP20: `{get_setting('network_fee_bep20')}` USDT\n"
        f"• عمولة سحب المنصة لـ TON: `{get_setting('network_fee_ton')}` USDT\n"
        f"• ساعات العمل: `{get_setting('work_hours')}`\n"
        f"• حالة استقبال المعاملات: **{current_status}**\n\n"
        "اختر البند المراد تحديثه لتعديله فوراً بالبوت:"
    )
    bot.reply_to(message, admin_msg, parse_mode="Markdown", reply_markup=markup)

# 7. واجهات الزبون والقائمة الرئيسية للبوت
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
    bot.reply_to(message, f"👋 أهلاً بك يا {message.from_user.first_name} في متجر وصرافة سوريا الآلية المحدثة الحية!", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = str(call.from_user.id)
    
    if call.data.startswith("set_") and user_id == ADMIN_CHAT_ID:
        setting_type = call.data.split("_")[1]
        user_trade_steps[user_id] = {"state": f"EDIT_{setting_type.upper()}"}
        
        prompt_texts = {
            "buy": "✏️ أرسل سعر **شراء** الـ USDT الخام بالليرة السورية:",
            "sell": "✏️ أرسل سعر **مبيع** الـ USDT الخام بالليرة السورية:",
            "mycomm": "✏️ أرسل قيمتك الربحية الشخصية المضافة بالليرة السورية لكل دولار:",
            "feetrc": "✏️ أرسل عمولة سحب شبكة TRC20 بالـ USDT:",
            "feebep": "✏️ أرسل عمولة سحب شبكة BEP20 بالـ USDT:",
            "feeton": "✏️ أرسل عمولة سحب شبكة TON بالـ USDT:",
            "hours": "✏️ أرسل نص أوقات العمل الجديد ليعرض للزبائن بالتفصيل:"
        }
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=prompt_texts[setting_type], parse_mode="Markdown")
        return
        
    elif call.data.startswith("status_") and user_id == ADMIN_CHAT_ID:
        new_status = call.data.split("_")[1]
        update_setting("bot_status", new_status)
        bot.answer_callback_query(call.id, "تم تحديث حالة الصرافة!")
        admin_panel(call.message)
        return

    if call.data == "browse_store":
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("🎮 ألعاب", callback_data="prod_games"),
            types.InlineKeyboardButton("💬 شات", callback_data="prod_chat"),
            types.InlineKeyboardButton("🌐 VPN", callback_data="prod_vpn")
        )
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🗂️ يرجى اختيار القسم لتصفحه مع حاسبة الأرباح التلقائية:", reply_markup=markup)
        
    elif call.data.startswith("prod_"):
        category = call.data.split("_")[1]
        bot.answer_callback_query(call.id, "🔄 جاري جلب المنتجات وتطبيق العمولة التلقائية...")
        products = fetch_mousa_products_by_category(category)
        
        if not products:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 العودة للأقسام", callback_data="browse_store"))
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚠️ هذا القسم قيد التحديث المؤقت حالياً من المصدر.", reply_markup=markup)
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for prod in products[:10]:
            final_p = calculate_custom_price(prod.get("rate", "0"))
            markup.add(types.InlineKeyboardButton(f"{prod.get('name')} | 💰 {final_p} SYP", callback_data=f"buy_{prod.get('id')}"))
        markup.add(types.InlineKeyboardButton("🔙 العودة للأقسام", callback_data="browse_store"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎁 المنتجات والخدمات المتاحة الحية بالليرة السورية شاملة الأرباح:", reply_markup=markup)

    elif call.data == "trade_usdt_main":
        if get_setting("bot_status") == "OFF":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu"))
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚠️ **عذراً منك يا غالي! قسم الصرافة متوقف مؤقتاً لتحديث الأسعار.**", parse_mode="Markdown", reply_markup=markup)
            return
            
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🟢 شراء USDT من البوت", callback_data="action_buy"),
            types.InlineKeyboardButton("🔴 بيع USDT إلى البوت", callback_data="action_sell")
        )
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu"))
        
        exchange_msg = (
            "🔄 **بوابة صرافة وتحويل الـ USDT الذكية**\n\n"
            f"⏰ **ساعات عمل قسم التداول:** `{get_setting('work_hours')}`\n"
            f"📈 **سعر الشراء الأساسي:** **{get_setting('usdt_buy_rate')} SYP**\n"
            f"📉 **سعر البيع الأساسي:** **{get_setting('usdt_sell_rate')} SYP**\n\n"
            "يرجى تحديد عمليتك وسيقوم البوت باحتساب العمولات ورسوم شبكة المنصة بدقة تفادياً لأي خسارة:"
        )
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=exchange_msg, parse_mode="Markdown", reply_markup=markup)
        
    elif call.data.startswith("action_"):
        action_raw = call.data.split("_")[1]
        action_type = "شراء" if action_raw == "buy" else "بيع"
        user_trade_steps[user_id] = {"action": action_type, "action_raw": action_raw}
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔹 TRC20", callback_data="net_TRC20"),
            types.InlineKeyboardButton("🔸 BEP20", callback_data="net_BEP20"),
            types.InlineKeyboardButton("💎 TON Network", callback_data="net_TON")
        )
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"⚙️ لقد حددت معاملة: **{action_type} USDT**\n\nالآن، يرجى تحديد نوع الشبكة لفرز العمولات ورسوم السحب من المنصة:", parse_mode="Markdown", reply_markup=markup)
        
    elif call.data.startswith("net_"):
        network = call.data.split("_")[1]
        if user_id in user_trade_steps:
            user_trade_steps[user_id]["network"] = network
            user_trade_steps[user_id]["state"] = "WAIT_AMOUNT"
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"🔢 شبكة التداول: **{network}**\n\nيرجى كتابة **الكمية الصافية من الـ USDT المراد استلامها أو تسليمها** (أرقام فقط):", parse_mode="Markdown")

    elif call.data == "deposit_wallet" or call.data == "main_menu":
        if user_id in user_trade_steps: del user_trade_steps[user_id]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🛒 تصفح المتجر (ألعاب وتطبيقات)", callback_data="browse_store"),
            types.InlineKeyboardButton("🔄 شراء ومبيع USDT / صرافة آلي", callback_data="trade_usdt_main"),
            types.InlineKeyboardButton("💰 شحن محفظة البوت (Sham Cash)", callback_data="deposit_wallet")
        )
        if call.data == "deposit_wallet":
            deposit_text = f"💰 **شحن محفظة المتجر المحلية عن طريق (Sham Cash)**\n\n📌 **رقم حساب Sham Cash الرسمي والمعتمد للمتجر:**\n`{MY_WALLETS['SHAM_CASH']}`\n\nيرجى تحويل الرصيد المطلوب، ثم أرسل لقطة شاشة للوصل المالي للدعم الفني لتفعيل حسابك فوراً."
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=deposit_text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🗂️ القائمة الرئيسية لمتجر سوريا المطور متاح أمامك الآن:", reply_markup=markup)

# 8. إدارة الرسائل وحساب العمولات الشبكية لحماية رأس المال
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = str(message.from_user.id)
    
    if user_id == ADMIN_CHAT_ID and user_id in user_trade_steps and user_trade_steps[user_id].get("state", "").startswith("EDIT_"):
        state = user_trade_steps[user_id]["state"]
        new_value = message.text
        
        key_mapping = {
            "EDIT_BUY": "usdt_buy_rate", "EDIT_SELL": "usdt_sell_rate",
            "EDIT_MYCOMM": "my_commission", "EDIT_FEETRC": "network_fee_trc20",
            "EDIT_FEEBEP": "network_fee_bep20", "EDIT_FEETON": "network_fee_ton",
            "EDIT_HOURS": "work_hours"
        }
        
        if state in key_mapping:
            update_setting(key_mapping[state], new_value)
            bot.reply_to(message, f"✅ تم حفظ وتحديث القيمة بنجاح إلى: `{new_value}`")
            
        del user_trade_steps[user_id]
        return

    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_AMOUNT":
        amount_text = message.text
        try:
            amount = float(amount_text)
            if amount <= 0: raise ValueError
        except ValueError:
            bot.reply_to(message, "⚠️ **خطأ في الإدخال!** يرجى إرسال الكمية المطلوبة بشكل أرقام صحيحة فقط وبدون رموز (مثال: 50):")
            return
            
        user_trade_steps[user_id]["amount"] = amount_text
        user_trade_steps[user_id]["state"] = "WAIT_RECEIPT"
        
        action_raw = user_trade_steps[user_id]["action_raw"]
        action = user_trade_steps[user_id]["action"]
        network = user_trade_steps[user_id]["network"]
        
        buy_rate = float(get_setting("usdt_buy_rate"))
        sell_rate = float(get_setting("usdt_sell_rate"))
        my_comm = float(get_setting("my_commission"))
        net_fee_usdt = float(get_setting(f"network_fee_{network.lower()}"))
        
        if action_raw == "buy":
            final_rate = buy_rate + my_comm
            total_usdt_needed = amount + net_fee_usdt
            total_syp = total_usdt_needed * final_rate
            
            calc_text = (
                f"💰 **حساب التكلفة الإجمالية الشاملة للعمولات والمنصة:**\n"
                f"• سعر الصرف مع عمولتك: `{final_rate:,.0f} SYP`\n"
                f"• رسوم سحب شبكة المنصة ({network}): `{net_fee_usdt} USDT`\n"
                f"• إجمالي الكمية المطلوب دفع قيمتها: `{total_usdt_needed} USDT`\n"
                f"🔥 **الصافي المطلوب تحويله عبر شام كاش:** **{total_syp:,.0f} ليرة سورية**"
            )
            target_wallet = MY_WALLETS["SHAM_CASH"]
            wallet_title = "حساب Sham Cash السوري المعتمد للمتجر"
        else:
            total_syp = amount * sell_rate
            calc_text = (
                f"💰 **حساب القيمة المستلمة الشاملة:**\n"
                f"• سعر صرف المبيع المعتمد: `{sell_rate:,.0f} SYP`\n"
                f"🔥 **المبلغ النهائي الذي ستستلمه كاش:** **{total_syp:,.0f} ليرة سورية**\n"
                f"⚠️ *ملاحظة: تأكد من إرسال الكمية كاملة لكي تصل صافية لمحفظتنا.*"
            )
            target_wallet = MY_WALLETS.get(network, "غير متوفر")
            wallet_title = f"عنوان محفظة USDT الرسمية لشبكة ({network})"
            
        instruction_msg = (
            f"✅ **ملخص طلب الصرافة المحمي والمحسوب بدقة:**\n"
            f"• نوع المعاملة: {action} USDT\n"
            f"• الكمية المستهدفة: {amount_text} USDT\n"
            f"• الشبكة المطلوبة: {network}\n\n"
            f"{calc_text}\n\n"
            f"📥 **الرجاء التحويل الفعلي الآن لعنوان الحساب التالي ومطابقة المبالغ:**\n"
            f"📌 {wallet_title}:\n"
            f"`{target_wallet}`\n\n"
            f"📸 **الخطوة الأخيرة:** بعد إتمام التحويل المالي الفعلي، يرجى إرسال **صورة إيصال التحويل (Screenshot)** هنا مباشرة لتأكيد طلبك وتمريره لغرفة المراجعة الحية للإدارة."
        )
        bot.reply_to(message, instruction_msg, parse_mode="Markdown")

# 9. استقبال الإيصالات وتوجيه التقارير لغرفة الإدارة العليا
@bot.message_handler(content_types=['photo'])
def receive_receipt_photo(message):
    user_id = str(message.from_user.id)
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_RECEIPT":
        bot.reply_to(message, "❤️ **شكراً لثقتك بنا يا غالي!** تم استلام لقطة شاشة الإيصال بنجاح وتمرير المعاملة والعمولات المحسوبة لغرفة مراجعة الإدارة الحية الآن.\n\n⏳ يرجى الانتظار قليلاً لحين المطابقة وتأكيد طلبك فورا.")
        
        photo_file_id = message.photo[-1].file_id
        action = user_trade_steps[user_id]["action"]
        action_raw = user_trade_steps[user_id]["action_raw"]
        network = user_trade_steps[user_id]["network"]
        amount = float(user_trade_steps[user_id]["amount"])
        
        buy_rate = float(get_setting("usdt_buy_rate"))
        sell_rate = float(get_setting("usdt_sell_rate"))
        my_comm = float(get_setting("my_commission"))
        net_fee_usdt = float(get_setting(f"network_fee_{network.lower()}"))
        
        if action_raw == "buy":
            final_rate = buy_rate + my_comm
            total_usdt = amount + net_fee_usdt
            total_syp = total_usdt * final_rate
            details_text = f"• كمية العميل المطلوبة: `{amount} USDT`\n• رسوم سحب المنصة: `{net_fee_usdt} USDT`\n• الإجمالي بالـ USDT المطلوب: `{total_usdt} USDT`\n• سعر الصرف المعتمد بالإرباح: `{final_rate} SYP`\n• إجمالي المطالبة (شام كاش): `{total_syp:,.0f} SYP`"
        else:
            total_syp = amount * sell_rate
            details_text = f"• كمية العميل المرسلة: `{amount} USDT`\n• سعر مبيع الصرف الخام: `{sell_rate} SYP`\n• إجمالي المطلوب تسليمه للعميل كاش: `{total_syp:,.0f} SYP`"
            
        admin_report_text = (
            f"🚨 **طلب صرافة مالي جديد وارد ومحسوب العمولات والشبكة تلقائياً!**\n\n"
            f"👤 **بيانات العميل:**\n"
            f"• الاسم: {message.from_user.first_name}\n"
            f"• اليوزر: @{message.from_user.username if message.from_user.username else 'لا يوجد'}\n"
            f"• الآيدي: `{user_id}`\n\n"
            f"⚙️ **تقرير الحسبة والعمولات المستحقة (مؤمن ضد الخسارة):**\n"
            f"• المعاملة المتخذة: *{action} USDT*\n"
            f"• الشبكة والمسار: *{network}*\n"
            f"{details_text}\n\n"
            f"👇 صورة الإيصال أو الوصل المرفق للمطابقة الحية اليدوية:"
        )
        try: bot.send_photo(ADMIN_CHAT_ID, photo_file_id, caption=admin_report_text, parse_mode="Markdown")
        except Exception as e: logger.error(f"❌ خطأ في تحويل الإيصال للأدمن: {e}")
        del user_trade_steps[user_id]

# 10. خادم ويب مدمج للبقاء حياً 24/7 دون توقف على سحابة Render
async def handle_render_web_request(request):
    return web.Response(text="Syria Anti-Loss Exchange Bot Core Operating Smoothly with Fresh Active Token!")

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
    web_thread = threading.Thread(target=start_isolated_web_server, daemon=True)
    web_thread.start()
    bot.infinity_polling()
