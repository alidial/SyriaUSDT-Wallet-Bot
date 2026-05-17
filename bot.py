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

# إعداد السجلات (Logs)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- البيانات الأساسية للبوت والـ API ---
BOT_TOKEN = "8859151257:AAFmgk1WvvSwaMwJJMywEAXqcX1gQX99NqM"
ADMIN_CHAT_ID = "926536751"
SUPPORT_LINK = "https://t.me/Syrusdt"

MOUSA_API_TOKEN = "C2BBglYMi2_xlgNy548z6MGu5OwQVUsbHuF6c_6PWgvp6bvdItov3ktXxxmQ2jHN"
MOUSA_API_BASE_URL = "https://mousa-card.com/api/v2"

MY_WALLETS = {
    "BEP20": "0x6567Dc3Dad88274B121d651679778C0aB9f87804",
    "TON": "UQDbXMU9L45iztaFrwQdXMMqd6pMjsDPma4Jba_pWTRnSfEa",
    "TRC20 (TRX)": "0x6567Dc3Dad88274B121d651679778C0aB9f87804",
    "SHAM_CASH": "7a93267a0832f55f8b35abeaf28f8960"
}

# حالات المحادثة المتعددة
(SELECT_NETWORK, WAIT_AMOUNT, WAIT_RECEIPT, WAIT_SHAM_CASH, WAIT_USER_MESSAGE, 
 WAIT_SET_BUY, WAIT_SET_SELL, WAIT_BROADCAST,
 WAIT_SET_START_HOUR, WAIT_SET_END_HOUR, WAIT_SERVICE_QUANTITY, WAIT_SEARCH_QUERY,
 WAIT_WALLET_DEPOSIT_AMT, WAIT_DEPOSIT_RECEIPT) = range(14)

# --- دالة الحساب الديناميكي المحدثة حسب عدد خانات السعر ---
def calculate_custom_price(original_price_str):
    try:
        raw_price = float(original_price_str)
        price_int = int(raw_price)
        num_digits = len(str(price_int))

        if num_digits == 3: addition = 5
        elif num_digits == 4: addition = 10
        elif num_digits == 5: addition = 15
        elif num_digits >= 6: addition = 20
        else: addition = 5

        final_price = raw_price + addition
        return math.ceil(final_price)
    except (ValueError, TypeError): return 0

# --- دالة جلب خدمات موسى كارد حياً ---
async def fetch_mousa_card_services():
    url = f"{MOUSA_API_BASE_URL}/services"
    headers = {
        "Authorization": f"Bearer {MOUSA_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list): return data
                    if isinstance(data, dict): return data.get("services", data.get("data", []))
                return []
    except Exception as e:
        logger.error(f"Failed to connect to Mousa Card API: {e}")
        return []

# --- تهيئة قاعدة البيانات المحلية ونظام المحفظة المدمج ---
def init_local_db():
    conn = sqlite3.connect("usdt_store.db")
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('buy_rate', '1330.0')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sell_rate', '1363.0')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sell_available', 'True')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('start_hour', '10')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('end_hour', '2')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_break', 'False')")
    
    # جدول المحافظ الخاص بالزبائن بالليرة السورية
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users_wallets (
            user_id TEXT PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, action TEXT,
            network TEXT, amount TEXT, total_cash TEXT, user_wallet TEXT, photo_file_id TEXT,
            status TEXT DEFAULT 'pending', timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_local_db()

def get_db_connection():
    conn = sqlite3.connect("usdt_store.db")
    conn.row_factory = sqlite3.Row
    return conn

# --- دوال إدارة رصيد المحفظة ---
def get_user_balance(user_id, username=""):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users_wallets WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone()
    if row:
        conn.close()
        return row['balance']
    else:
        cur.execute("INSERT INTO users_wallets (user_id, username, balance) VALUES (?, ?, 0.0)", (str(user_id), username))
        conn.commit()
        conn.close()
        return 0.0

def update_user_balance(user_id, amount):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users_wallets WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone()
    if row:
        new_bal = row['balance'] + amount
        cur.execute("UPDATE users_wallets SET balance = ? WHERE user_id = ?", (new_bal, str(user_id)))
    conn.commit()
    conn.close()

def build_three_column_keyboard(services_list, context):
    buttons = []
    row = []
    for srv in services_list:
        srv_id = str(srv.get("service", srv.get("id", "")))
        srv_name = srv.get("name", "خدمة")
        raw_price = srv.get("rate", srv.get("price", "0"))
        custom_price = calculate_custom_price(raw_price)
        if srv_id and custom_price > 0:
            context.bot_data[f"mousa_srv_{srv_id}"] = {"name": srv_name, "price": custom_price}
            btn_text = f"{custom_price:,.0f} ل.س"
            row.append(InlineKeyboardButton(btn_text, callback_data=f"req_mousa_{srv_id}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
    if row: buttons.append(row)
    return buttons

def get_rates_from_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    settings = {r['key']: r['value'] for r in cur.fetchall()}
    conn.close()
    return (float(settings.get('buy_rate', 1330.0)), float(settings.get('sell_rate', 1363.0)),
            settings.get('sell_available', 'True') == 'True', int(settings.get('start_hour', 10)),
            int(settings.get('end_hour', 2)), settings.get('bot_break', 'False') == 'True')

def update_db_setting(key, value):
    conn = get_db_connection()
    conn.cursor().execute("UPDATE settings SET value = ? WHERE key = ?", (str(value), key))
    conn.commit()
    conn.close()

def save_order_to_db(user_id, username, action, network, amount, total_cash=None, user_wallet=None, photo_file_id=None):
    conn = get_db_connection()
    cur = conn.cursor()
    now_str = datetime.now(pytz.timezone('Asia/Damascus')).strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("""
        INSERT INTO orders (user_id, username, action, network, amount, total_cash, user_wallet, photo_file_id, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (str(user_id), username, action, network, str(amount), str(total_cash), user_wallet, photo_file_id, now_str))
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    return order_id

async def safe_answer(query, text: str = ""):
    try: await query.answer(text)
    except BadRequest: pass

def is_within_working_hours():
    _, _, _, start_h, end_h, is_break = get_rates_from_db()
    if is_break: return False
    current_hour = datetime.now(pytz.timezone('Asia/Damascus')).hour
    return start_h <= current_hour < end_h if start_h <= end_h else current_hour >= start_h or current_hour < end_h

def calculate_buy_from_user_fee(amount):
    if 1 <= amount <= 10: return 1.30
    elif 11 <= amount <= 20: return 2.20
    elif 21 <= amount <= 35: return 2.50
    elif 36 <= amount <= 60: return 3.00
    return amount * 0.05 if amount >= 61 else 0.0

def calculate_sell_to_user_fee(amount):
    return 2.0 if amount <= 10 else (2.0 + (math.ceil((amount - 10) / 3.0) * 0.10) if amount <= 100 else amount * 0.03)

# --- كيبورد الواجهة الرئيسية المحدث بنظام المحافظ ---
def get_main_keyboard(context: ContextTypes.DEFAULT_TYPE, user_id, username):
    buy_rate, sell_rate, sell_available, _, _, _ = get_rates_from_db()
    bal = get_user_balance(user_id, username)
    sell_btn_text = f"📤 شراء USDT من البوت • {sell_rate:,.0f} ل.س" if sell_available else "📤 شراء USDT (منتهي حالياً ❌)"
    
    keyboard = [
        [InlineKeyboardButton(f"💳 محفظتك الحالية: {bal:,.0f} ل.س", callback_data="wallet_info")],
        [InlineKeyboardButton("📥 تعبئة رصيد المحفظة كاش", callback_data="deposit_wallet")],
        [InlineKeyboardButton("📊 أسعار الصرف", callback_data="rates"), InlineKeyboardButton("🧮 حاسبة الأسعار", callback_data="user_calc")],
        [InlineKeyboardButton(f"📥 بيع USDT للبوت • {buy_rate:,.0f} ل.س", callback_data="action_buy_from_user")],
        [InlineKeyboardButton(sell_btn_text, callback_data="action_sell_to_user")],
        [InlineKeyboardButton("🎁 خدمات شحن موسى كارد (ألعاب وبث حيوية)", callback_data="digital_offers_main")],
        [InlineKeyboardButton("📋 حالة طلباتي", callback_data="check_status"), InlineKeyboardButton("📞 الدعم الفني", callback_data="contact_via_bot")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_dashboard_keyboard():
    buy_rate, sell_rate, sell_available, start_h, end_h, is_break = get_rates_from_db()
    keyboard = [
        [InlineKeyboardButton(f"💰 شراء ({buy_rate:,.0f})", callback_data="adm_edit_buy"), InlineKeyboardButton(f"💰 مبيع ({sell_rate:,.0f})", callback_data="adm_edit_sell")],
        [InlineKeyboardButton("🔄 المبيع: " + ("🟢 متاح" if sell_available else "🔴 مغلق"), callback_data="adm_toggle_sell"), InlineKeyboardButton("☕️ استراحة: " + ("مشغل" if is_break else "معطل"), callback_data="adm_toggle_break")],
        [InlineKeyboardButton(f"⏱ بدء ({start_h}:00)", callback_data="adm_set_start"), InlineKeyboardButton(f"⏱ نهاية ({end_h}:00)", callback_data="adm_set_end")],
        [InlineKeyboardButton("📈 تقرير الخزينة اليومي", callback_data="adm_daily_report"), InlineKeyboardButton("📢 رسالة جماعية", callback_data="adm_broadcast")],
        [InlineKeyboardButton("🏠 قائمة المستخدمين الرئيسية", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_control_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]])
def get_services_back_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة لقسم الشحن", callback_data="digital_offers_main")]])
def get_networks_keyboard(action_type):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🌐 BEP20", callback_data=f"net_{action_type}_BEP20")],[InlineKeyboardButton("💎 TON", callback_data=f"net_{action_type}_TON")],[InlineKeyboardButton("⚡ TRC20 (TRX)", callback_data=f"net_{action_type}_TRX")],[InlineKeyboardButton("🔙 إلغاء والعودة", callback_data="main_menu")]])

# --- المنطق الوظيفي للبوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    if str(user.id) == ADMIN_CHAT_ID:
        await (update.message.reply_text("⚙️ **لوحة التحكم المتكاملة للأدمن:**", reply_markup=get_admin_dashboard_keyboard(), parse_mode="Markdown") if update.message else update.callback_query.message.edit_text("⚙️ **لوحة التحكم المتكاملة للأدمن:**", reply_markup=get_admin_dashboard_keyboard(), parse_mode="Markdown"))
        return ConversationHandler.END
    
    welcome_text = "🟢 **مرحباً بك في بوت صرافة USDT وشحن الألعاب السوري بنظام المحافظ المسبقة الدفع!**\n\nيمكنك الآن تعبئة رصيدك عبر شام كاش والشحن فوراً دون أي انتظار."
    if update.message: await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(context, user.id, user.username or user.first_name), parse_mode="Markdown")
    elif update.callback_query: await update.callback_query.message.edit_text(welcome_text, reply_markup=get_main_keyboard(context, user.id, user.username or user.first_name), parse_mode="Markdown")
    return ConversationHandler.END

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user
    
    if query.data == "main_menu":
        await start(update, context)
        return ConversationHandler.END
    
    elif query.data == "wallet_info":
        bal = get_user_balance(user.id, user.username or user.first_name)
        await query.message.edit_text(f"💳 **تفاصيل محفظتك الإلكترونية:**\n\nرصيدك الحالي المتاح: **{bal:,.0f} ل.س**\n\nيمكنك استخدام هذا الرصيد لشحن أي لعبة أو برنامج بث أو VPN فوراً من قسم الخدمات.", reply_markup=get_control_keyboard(), parse_mode="Markdown")
        return ConversationHandler.END

    elif query.data == "deposit_wallet":
        await query.message.edit_text("✍️ **قم بكتابة المبلغ الذي تود شحنه في محفظتك بالليرة السورية (أرقام فقط):**\nمثال: `50000`", reply_markup=get_control_keyboard(), parse_mode="Markdown")
        return WAIT_WALLET_DEPOSIT_AMT

    elif query.data == "rates":
        buy_rate, sell_rate, _, start_h, end_h, _ = get_rates_from_db()
        await query.message.edit_text(f"📊 **أسعار الصرف وأوقات العمل الحالية:**\n\n📥 بيعك للبوت: **{buy_rate:,.0f} ل.س**\n📤 شراؤك من البوت: **{sell_rate:,.0f} ل.س**\n\n⏰ العمل: من **{start_h}:00** إلى **{end_h}:00**.", reply_markup=get_control_keyboard(), parse_mode="Markdown")
        return ConversationHandler.END

    elif query.data == "user_calc":
        context.user_data["is_calculating"] = True
        await query.message.edit_text("🧮 **أرسل كمية الـ USDT للاستفسار عن سعرها بالليرة السورية:**", reply_markup=get_control_keyboard(), parse_mode="Markdown")
        return ConversationHandler.END

    elif query.data == "digital_offers_main":
        await query.message.edit_text("⏳ جاري سحب أحدث الألعاب والـ VPN باللغتين العربية والانكليزية من موسى كارد...")
        services = await fetch_mousa_card_services()
        if not services:
            await query.message.edit_text("⚠️ فشل جلب البيانات، حاول لاحقاً.", reply_markup=get_control_keyboard())
            return ConversationHandler.END
        context.user_data["all_cached_services"] = services
        menu_buttons = [[InlineKeyboardButton("🔍 📑 ابحث عن لعبة / برنامج / VPN", callback_data="start_search_srv")]]
        srv_buttons = build_three_column_keyboard(services[:60], context)
        menu_buttons.extend(srv_buttons)
        menu_buttons.append([InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")])
        await query.message.edit_text("🎁 **قائمة الأسعار المباشرة بـ 3 أعمدة (اضغط على السعر للمعاينة والطلب):**", reply_markup=InlineKeyboardMarkup(menu_buttons), parse_mode="HTML")
        return ConversationHandler.END

    elif query.data == "start_search_srv":
        await query.message.edit_text("🔍 أرسل اسم المادة التي تبحث عنها باللغة العربية أو الإنكليزية (ببجي، pubg، vpn):", reply_markup=get_services_back_keyboard())
        return WAIT_SEARCH_QUERY

    elif query.data.startswith("req_mousa_"):
        srv_id = query.data.replace("req_mousa_", "")
        srv_info = context.bot_data.get(f"mousa_srv_{srv_id}", {"name": srv_id, "price": 0})
        context.user_data["selected_service"] = srv_info["name"]
        context.user_data["selected_price"] = srv_info["price"]
        
        # 💵 فحص رصيد محفظة الزبون تلقائياً قبل تأكيد الطلب
        bal = get_user_balance(user.id)
        if bal < srv_info["price"]:
            await query.message.edit_text(f"❌ **رصيد محفظتك غير كافٍ للاتمام!**\n\n📌 الخدمة: **{srv_info['name']}**\n💰 سعرها: **{srv_info['price']:,.0f} ل.س**\n💳 رصيدك الحالي: **{bal:,.0f} ل.س**\n\nيرجى شحن محفظتك أولاً عبر القائمة الرئيسية للمتابعة.", reply_markup=get_control_keyboard(), parse_mode="Markdown")
            return ConversationHandler.END
            
        await query.message.edit_text(f"🛒 **تفاصيل الطلب (الدفع عبر المحفظة):**\n📌 الخدمة: **{srv_info['name']}**\n💰 السعر: **{srv_info['price']:,.0f} ل.س**\n\n✍️ أرسل معرف حسابك (ID أو اليوزر) بدقة بالغة ليتم الخصم والشحن فوراً:", reply_markup=get_services_back_keyboard(), parse_mode="Markdown")
        return WAIT_SERVICE_QUANTITY

    elif query.data in ["action_buy_from_user", "action_sell_to_user"]:
        if not is_within_working_hours():
            await query.message.edit_text("❌ نحن خارج أوقات العمل الرسمية حالياً.", reply_markup=get_control_keyboard())
            return ConversationHandler.END
        action = "buy" if query.data == "action_buy_from_user" else "sell"
        context.user_data["action"] = action
        await query.message.edit_text("🌐 **اختر شبكة التحويل المطلوبة:**", reply_markup=get_networks_keyboard(action))
        return SELECT_NETWORK

# --- معالجة شحن الرصيد بالمحفظة للمستخدم ---
async def receive_wallet_deposit_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ يرجى إرسال رقم صحيح للمبلغ:")
        return WAIT_WALLET_DEPOSIT_AMT
    context.user_data["deposit_amount"] = amount
    instructions = f"⚠️ **شحن محفظة إلكترونية بقيمة {amount:,.0f} ل.س**\n\nقم بتحويل المبلغ المطلق لحساب شام كاش التالي:\n`{MY_WALLETS['SHAM_CASH']}`\n\n📸 بعد التحويل، يرجى إرسال صورة إشعار الدفع الواضح هنا فوراً للتوثيق:"
    await update.message.reply_text(instructions, parse_mode="Markdown", reply_markup=get_control_keyboard())
    return WAIT_WALLET_DEPOSIT_RE_C

async def receive_deposit_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("❌ يرجى إرسال صورة الإشعار (لقطة الشاشة للتحويل المالي):")
        return WAIT_WALLET_DEPOSIT_RE_C
    
    photo_id = update.message.photo[-1].file_id
    dep_amt = context.user_data.get("deposit_amount", 0)
    
    # حياكة الأزرار للأدمن لتعبئة الرصيد بضغطة واحدة
    admin_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ موافقة وتعبئة رصيده", callback_data=f"wlt_approve_{user.id}_{dep_amt}")],
        [InlineKeyboardButton("❌ رفض الطلب", callback_data=f"wlt_reject_{user.id}")]
    ])
    
    caption = f"💳 <b>طلب شحن محفظة عميل مسبق</b>\n👤 العميل: {user.mention_html()}\n💰 المبلغ المطلوب تعبئته: <b>{dep_amt:,.0f} ل.س</b>"
    await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=admin_markup)
    await update.message.reply_text("✅ **تم رفع إشعار شحن محفظتك إلى الصراف المسؤول بنجاح!**\nسيتم مراجعته وإضافة الرصيد إلى حسابك فوراً.", reply_markup=get_control_keyboard())
    return ConversationHandler.END

# --- معالجة طلب شحن الألعاب عبر رصيد المحفظة المستقطع ---
async def process_service_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id_input = update.message.text.strip()
    srv_name = context.user_data.get("selected_service")
    srv_price = context.user_data.get("selected_price", 0)
    
    # الخصم من محفظة العميل فوراً
    update_user_balance(user.id, -srv_price)
    new_bal = get_user_balance(user.id)
    
    admin_alert = f"🎁 <b>طلب شحن من المحفظة (مستقطع ومكتمل الرصيد)</b>\n👤 العميل: {user.mention_html()}\n📌 الخدمة: <b>{srv_name}</b>\n💰 السعر المخصوم: <b>{srv_price:,.0f} ل.س</b>\n🆔 الـ ID المطلوب شحنه: <code>{user_id_input}</code>\n\n🟢 <u>الرصيد مدفوع من المحفظة، قم بالشحن للعميل فوراً!</u>"
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_alert, parse_mode="HTML")
    
    await update.message.reply_text(f"✅ **تم خصم {srv_price:,.0f} ل.س من محفظتك الإلكترونية بنجاح!**\n\n📌 رصيدك المتبقي الحالي: **{new_bal:,.0f} ل.س**\n🚀 تم تمرير الـ ID المكتوب للإدارة وجاري شحن الخدمة لك بلمح البصر.", reply_markup=get_control_keyboard(), parse_mode="Markdown")
    return ConversationHandler.END

# --- دالة البحث الذكي بـ 3 أعمدة ---
async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_text = update.message.text.strip().lower()
    services = context.user_data.get("all_cached_services") or await fetch_mousa_card_services()
    context.user_data["all_cached_services"] = services
    
    filtered = [srv for srv in services if search_text in srv.get("name", "").lower()]
    if not filtered:
        await update.message.reply_text(f"❌ لم يعثر على نتائج لـ: <b>{update.message.text}</b>\nحاول مجدداً باسم آخر:", reply_markup=get_services_back_keyboard(), parse_mode="HTML")
        return WAIT_SEARCH_QUERY
        
    menu_buttons = [[InlineKeyboardButton("🔍 ابحث عن مادة أخرى", callback_data="start_search_srv")]]
    srv_buttons = build_three_column_keyboard(filtered[:45], context)
    menu_buttons.extend(srv_buttons)
    menu_buttons.append([InlineKeyboardButton("🔙 العودة لقسم الشحن", callback_data="digital_offers_main")])
    await update.message.reply_text(f"🎯 <b>نتائج البحث بـ 3 أعمدة لـ ({update.message.text}):</b>", reply_markup=InlineKeyboardMarkup(menu_buttons), parse_mode="HTML")
    return ConversationHandler.END

# --- بقية دوال الصرافة المعتادة للـ USDT والآدمن ---
async def select_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    context.user_data["network"] = "TRC20 (TRX)" if query.data.split("_")[2] == "TRX" else query.data.split("_")[2]
    await query.message.edit_text("أرسل كمية الـ USDT المطلوبة (أرقام فقط):", reply_markup=get_control_keyboard())
    return WAIT_AMOUNT

async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أرسل رقماً صحيحاً فقط:")
        return WAIT_AMOUNT
    context.user_data["amount"] = amount
    action = context.user_data.get("action")
    network = context.user_data.get("network")
    buy_rate, sell_rate, _, _, _, _ = get_rates_from_db()
    if action == "buy":
        fee = calculate_buy_from_user_fee(amount)
        total_syp = (amount - fee) * buy_rate
        context.user_data["total_cash"] = total_syp
        await update.message.reply_text(f"⚠️ **قم بتحويل {amount} USDT** لعنوان شبكة **{network}**:\n`{MY_WALLETS.get(network, MY_WALLETS['TRC20 (TRX)'])}`\n\n💰 كاش مستحق لك: **{total_syp:,.0f} ل.س**\n📸 أرسل إشعار التحويل المالي:", parse_mode="Markdown", reply_markup=get_control_keyboard())
        return WAIT_RECEIPT
    else:
        fee_sell = calculate_sell_to_user_fee(amount)
        total_syp = (amount + fee_sell) * sell_rate
        context.user_data["total_cash"] = total_syp
        await update.message.reply_text(f"⚠️ **قم بتحويل مبلغ {total_syp:,.0f} ل.س** لحساب شام كاش:\n`{MY_WALLETS['SHAM_CASH']}`\n\n🎯 أرسل عنوان محفظتك لاستلام الـ USDT:", parse_mode="Markdown", reply_markup=get_control_keyboard())
        return WAIT_SHAM_CASH

async def receive_sham_cash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_address = update.message.text.strip()
    if len(user_address) < 5: return WAIT_SHAM_CASH
    context.user_data["user_wallet"] = user_address
    await update.message.reply_text("📸 أرسل صورة إشعار تحويل الأموال الواضح من تطبيق شام كاش:", reply_markup=get_control_keyboard())
    return WAIT_RECEIPT

async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo: return WAIT_RECEIPT
    photo_id = update.message.photo[-1].file_id
    order_id = save_order_to_db(user.id, user.username or user.first_name, context.user_data.get("action"), context.user_data.get("network"), context.user_data.get("amount"), context.user_data.get("total_cash"), context.user_data.get("user_wallet"), photo_id)
    admin_markup = InlineKeyboardMarkup([[InlineKeyboardButton("✅ موافقة", callback_data=f"adm_approve_{user.id}_{order_id}")],[InlineKeyboardButton("❌ رفض", callback_data=f"adm_reject_{user.id}")]])
    await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=photo_id, caption=f"📥 طلب صرافة #{order_id} من {user.mention_html()}", parse_mode="HTML", reply_markup=admin_markup)
    await update.message.reply_text("✅ تم استلام إشعار عملية الصرافة بنجاح وللتحقق بالإدارة.", reply_markup=get_control_keyboard())
    return ConversationHandler.END

async def handle_admin_dashboard_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    if query.data == "adm_edit_buy": return WAIT_SET_BUY
    elif query.data == "adm_edit_sell": return WAIT_SET_SELL
    elif query.data == "adm_toggle_sell":
        _, _, avail, _, _, _ = get_rates_from_db(); update_db_setting('sell_available', str(not avail))
        await query.message.edit_text("⚙️ تم تحديث الحالة!", reply_markup=get_admin_dashboard_keyboard())
    return ConversationHandler.END

# --- معالجة أزرار تعبئة المحافظ ورفضها للأدمن (الموزع) ---
async def handle_admin_global_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    data = query.data
    
    if data.startswith("wlt_approve_"):
        parts = data.split("_")
        target_uid = parts[2]
        amount_to_add = float(parts[3])
        
        # تفعيل الزيادة والشحن في رصيد محفظة العميل بقاعدة البيانات
        update_user_balance(target_uid, amount_to_add)
        new_b = get_user_balance(target_uid)
        
        try:
            await context.bot.send_message(chat_id=target_uid, text=f"✅ **تم تأكيد عملية الدفع بنجاح!**\n\n💰 تم إضافة **{amount_to_add:,.0f} ل.س** إلى محفظتك الإلكترونية.\n💳 رصيدك الإجمالي الحالي: **{new_b:,.0f} ل.س**.\n\nيمكنك الآن الشحن الفوري للألعاب من البوت مباشرة!", parse_mode="Markdown")
        except Exception: pass
        await query.edit_message_caption(caption=query.message.caption + f"\n\n✅ <b>[تمت الموافقة وشحن المحفظة بـ {amount_to_add:,.0f} ل.س]</b>", parse_mode="HTML")
        
    elif data.startswith("wlt_reject_"):
        target_uid = data.split("_")[2]
        try:
            await context.bot.send_message(chat_id=target_uid, text="❌ **تم رفض طلب شحن المحفظة!**\nالسبب: إشعار الدفع عبر شام كاش غير مطابق أو غير مكتمل الدفع.")
        except Exception: pass
        await query.edit_message_caption(caption=query.message.caption + "\n\n❌ <b>[تم الرفض]</b>", parse_mode="HTML")

async def handle_unexpected_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or str(update.effective_user.id) == ADMIN_CHAT_ID: return
    # حاسبة الأسعار العادية
    if context.user_data.get("is_calculating"):
        try:
            amt = float(update.message.text.strip())
            buy, sell, _, _, _, _ = get_rates_from_db()
            await update.message.reply_text(f"🧮 **نتائج الحساب لـ {amt} USDT:**\n\n📥 بيع للبوت: {(amt-calculate_buy_from_user_fee(amt))*buy:,.0f} ل.س\n📤 شراء من البوت: {(amt+calculate_sell_to_user_fee(amt))*sell:,.0f} ل.س", reply_markup=get_control_keyboard(), parse_mode="Markdown")
            context.user_data["is_calculating"] = False
            return
        except ValueError: pass
    await update.message.reply_text("0️⃣ يرجى استخدام أزرار التحكم بالقائمة الرئيسية للتحويل والمتابعة بشكل صحيح:", reply_markup=get_control_keyboard())

async def handle_ping(request): return web.Response(text="Wallet System & Mousa Card Live Server Ready ✅")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))).start()

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_web_server())
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(handle_buttons, pattern="^(rates|user_calc|action_buy_from_user|action_sell_to_user|check_status|contact_via_bot|main_menu|digital_offers_main|req_mousa_|wallet_info|deposit_wallet|start_search_srv)"),
            CallbackQueryHandler(handle_admin_dashboard_callbacks, pattern="^adm_(edit_|broadcast)"),
        ],
        states={
            SELECT_NETWORK: [CallbackQueryHandler(select_network, pattern="^net_")],
            WAIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
            WAIT_SHAM_CASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_sham_cash)],
            WAIT_RECEIPT: [MessageHandler(filters.PHOTO, receive_receipt)],
            WAIT_SERVICE_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_service_quantity)],
            WAIT_SEARCH_QUERY: [CallbackQueryHandler(handle_buttons, pattern="^(digital_offers_main|main_menu)$"), MessageHandler(filters.TEXT & ~filters.COMMAND, process_search_query)],
            WAIT_WALLET_DEPOSIT_AMT: [CallbackQueryHandler(handle_buttons, pattern="^main_menu$"), MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet_deposit_amt)],
            WAIT_WALLET_DEPOSIT_RE_C: [CallbackQueryHandler(handle_buttons, pattern="^main_menu$"), MessageHandler(filters.PHOTO, receive_deposit_receipt)]
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_admin_global_callbacks, pattern="^wlt_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_message))
    
    logger.info("تم إطلاق البوت المطور بالكامل بنظام المحافظ المدمج بنجاح...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
