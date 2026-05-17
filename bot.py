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

# 2. إعداد التوكن والآيدي الصحيح الخاص بك 🎯
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8859151257:AAF0SivQS_NiDcPaYiZFrt1p0Ep_T13lJTw")
ADMIN_CHAT_ID = "926536751"  # آيديك الصحيح والمثبت ✅

SUPPORT_LINK = "https://t.me/Syrusdt"

# عناوين المحافظ الرسمية المحدثة والصحيحة 🌐
MY_WALLETS = {
    "TRC20": "TAnv4K6gGk99G35uD71NymqXF2uC57xJAt",
    "BEP20": "0x6567Dc3Dad88274B121d651679778C0aB9f87804",  # تم تحديث عنوان BEP20 الجديد هنا بنجاح ✅
    "TON": "UQDbXMU9L45iztaFrwQdXMMqd6pMjsDPma4Jba_pWTRnSfEa",  
    "SHAM_CASH": "9542037"  # حساب شام كاش الصحيح
}

bot = telebot.TeleBot(BOT_TOKEN)
user_trade_steps = {}

# 3. تهيئة قاعدة البيانات المحلية لحفظ قيم الأسعار والنسب والعمولات
def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, balance REAL DEFAULT 0.0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    
    # أسعار الصرافة الافتراضية والنسب بالليرة السورية
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('usdt_buy_rate', '15000')") # سعر شراء المتجر من العميل
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('usdt_sell_rate', '15500')") # سعر مبيع المتجر للعميل
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('my_commission', '200')") # عمولتك الثابتة
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('network_fee_trc20', '1.5')") # رسوم شبكة TRC20 بالـ USDT
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('network_fee_bep20', '0.3')") # رسوم شبكة BEP20 بالـ USDT
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('network_fee_ton', '0.5')") # رسوم شبكة TON بالـ USDT
    
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

# 4. لوحة تحكم الأدمن المباشرة (/admin)
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != ADMIN_CHAT_ID:
        bot.reply_to(message, "❌ هذا الأمر مخصص حصرياً للإدارة.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💵 تعديل سعر الشراء", callback_data="set_buy"),
        types.InlineKeyboardButton("💵 تعديل سعر المبيع", callback_data="set_sell"),
        types.InlineKeyboardButton("💰 عمولة البوت المضافة", callback_data="set_mycomm"),
        types.InlineKeyboardButton("🌐 رسوم TRC20", callback_data="set_feetrc"),
        types.InlineKeyboardButton("🌐 رسوم BEP20", callback_data="set_feebep"),
        types.InlineKeyboardButton("🌐 رسوم TON", callback_data="set_feeton"),
        types.InlineKeyboardButton("⏰ ساعات العمل", callback_data="set_hours"),
        types.InlineKeyboardButton("🟢 تشغيل البوت", callback_data="status_ON"),
        types.InlineKeyboardButton("🔴 إيقاف البوت", callback_data="status_OFF")
    )
    current_status = "نشط ✅" if get_setting("bot_status") == "ON" else "متوقف مؤقتاً ❌"
    
    prices_info = (
        f"🛠️ **لوحة التحكم بالصرافة والنسب (الإدارة):**\n\n"
        f"• وضع البوت الحالي: {current_status}\n"
        f"• سعر الشراء الحالي: `{get_setting('usdt_buy_rate')}` SP\n"
        f"• سعر المبيع الحالي: `{get_setting('usdt_sell_rate')}` SP\n"
        f"• العمولة الثابتة: `{get_setting('my_commission')}` SP\n\n"
        f"اضغط على أي زر للتعديل الفوري عبر إرسال القيمة نصياً بعد الضغط:"
    )
    bot.reply_to(message, prices_info, parse_mode="Markdown", reply_markup=markup)

# 5. القائمة الرئيسية للنظام (صرافة وحوالات شام كاش فقط)
@bot.message_handler(commands=['start'])
def send_welcome(message):
    init_db()
    user_id = str(message.from_user.id)
    if user_id in user_trade_steps: del user_trade_steps[user_id]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔄 شراء ومبيع USDT / صرافة آلي", callback_data="trade_usdt_main"),
        types.InlineKeyboardButton("💰 حوالات وشحن المحفظة (شام كاش)", callback_data="deposit_wallet"),
        types.InlineKeyboardButton("📞 الدعم الفني المباشر", url=SUPPORT_LINK)
    )
    
    status_text = ""
    if get_setting("bot_status") == "OFF":
        status_text = "\n\n⚠️ تنويه: وضع الصرافة متوقف حالياً للتحديث!"

    bot.reply_to(message, f"👋 أهلاً بك يا {message.from_user.first_name} في بوت الصرافة وتحويل الـ USDT الذكي في سـوريا! 🇸🇾{status_text}", reply_markup=markup)

# 6. معالجة ضغطات الأزرار (Callback Queries)
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = str(call.from_user.id)
    
    if call.data.startswith("set_") and user_id == ADMIN_CHAT_ID:
        setting_type = call.data.split("_")[1]
        user_trade_steps[user_id] = {"state": f"EDIT_{setting_type.upper()}"}
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"✏️ أرسل القيمة الجديدة للبند المحدد حالياً بالأرقام:")
        return
    elif call.data.startswith("status_") and user_id == ADMIN_CHAT_ID:
        update_setting("bot_status", call.data.split("_")[1])
        admin_panel(call.message)
        return

    if call.data == "main_menu":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🔄 شراء ومبيع USDT / صرافة آلي", callback_data="trade_usdt_main"),
            types.InlineKeyboardButton("💰 حوالات وشحن المحفظة (شام كاش)", callback_data="deposit_wallet"),
            types.InlineKeyboardButton("📞 الدعم الفني المباشر", url=SUPPORT_LINK)
        )
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="👋 اختر العملية المطلوبة من القائمة:", reply_markup=markup)
        return

    # قسم الحوالات المباشر (شام كاش)
    if call.data == "deposit_wallet":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"💰 **بوابة الحوالات وشحن المحفظة (شام كاش):**\n\nيرجى تحويل مبلغ الحوالة إلى حسابنا التالي:\n`{MY_WALLETS['SHAM_CASH']}`\n\n📸 بعد إتمام التحويل، يرجى إرسال لقطة شاشة (Screenshot) للوصل هنا فوراً لتأكيد رصيدك يدوياً من الإدارة.", parse_mode="Markdown", reply_markup=markup)
        return

    # قسم الصرافة وحساب أسعار الـ USDT بالليرة
    if call.data == "trade_usdt_main":
        if get_setting("bot_status") == "OFF":
            bot.answer_callback_query(call.id, "⚠️ قسم الصرافة متوقف مؤقتاً لتحديث الأسعار.")
            return
            
        buy_rate = get_setting("usdt_buy_rate")
        sell_rate = get_setting("usdt_sell_rate")
        work_hours = get_setting("work_hours")
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🟢 شراء USDT", callback_data="action_buy"),
            types.InlineKeyboardButton("🔴 بيع USDT", callback_data="action_sell")
        )
        markup.add(types.InlineKeyboardButton("🔙 العودة للمنزل", callback_data="main_menu"))
        
        msg_text = (
            f"📊 **أسعار صرف الـ USDT الحالية بالليرة السورية:**\n\n"
            f"🟢 نبيعك الـ USDT بسعر: **{sell_rate} SP**\n"
            f"🔴 نشتري منك الـ USDT بسعر: **{buy_rate} SP**\n\n"
            f"⏰ ساعات العمل والتحويل الحقيقي: `{work_hours}`\n\n"
            f"اختر العملية المطلوبة للبدء بها:"
        )
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg_text, parse_mode="Markdown", reply_markup=markup)
        return

    if call.data.startswith("action_"):
        action = call.data.split("_")[1]
        user_trade_steps[user_id] = {"action_raw": action}
        
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("🌐 TRC20", callback_data="net_TRC20"),
            types.InlineKeyboardButton("🌐 BEP20", callback_data="net_BEP20"),
            types.InlineKeyboardButton("🌐 TON", callback_data="net_TON")
        )
        markup.add(types.InlineKeyboardButton("🔙 إلغاء والعودة", callback_data="trade_usdt_main"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚙️ يرجى اختيار شبكة التحويل المطلوبة لحساب العمولات ورسوم النقل بدقة:", reply_markup=markup)
        return

    if call.data.startswith("net_"):
        network = call.data.split("_")[1]
        if user_id in user_trade_steps:
            user_trade_steps[user_id]["network"] = network
            user_trade_steps[user_id]["state"] = "WAIT_AMOUNT"
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"🔢 أرسل كمية الـ **USDT** المطلوبة الآن (أرقام فقط، مثال: 50):", parse_mode="Markdown")
        return

# 7. إدارة الرسائل النصية المباشرة والعمليات الحسابية
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = str(message.from_user.id)
    
    if user_id == ADMIN_CHAT_ID and user_id in user_trade_steps and str(user_trade_steps[user_id].get("state", "")).startswith("EDIT_"):
        state = user_trade_steps[user_id]["state"]
        key_mapping = {
            "EDIT_BUY": "usdt_buy_rate", 
            "EDIT_SELL": "usdt_sell_rate", 
            "EDIT_MYCOMM": "my_commission", 
            "EDIT_FEETRC": "network_fee_trc20", 
            "EDIT_FEEBEP": "network_fee_bep20", 
            "EDIT_FEETON": "network_fee_ton", 
            "EDIT_HOURS": "work_hours"
        }
        if state in key_mapping:
            update_setting(key_mapping[state], message.text)
            bot.reply_to(message, f"✅ تم تحديث القيمة وحفظها بنجاح في قاعدة البيانات.")
        del user_trade_steps[user_id]
        return

    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_AMOUNT":
        try:
            amount = float(message.text)
            action = user_trade_steps[user_id]["action_raw"]
            network = user_trade_steps[user_id]["network"]
            
            rate = float(get_setting("usdt_sell_rate" if action == "buy" else "usdt_buy_rate"))
            my_commission = float(get_setting("my_commission"))
            network_fee = float(get_setting(f"network_fee_{network.lower()}"))
            
            if action == "buy": # العميل يشتري USDT
                total_usdt_needed = amount + network_fee
                total_sp_cost = (total_usdt_needed * rate) + my_commission
                summary_text = (
                    f"📊 **تفاصيل فاتورة تحويل وشراء USDT:**\n\n"
                    f"• الكمية الصافية المطلوبة: `{amount}` USDT\n"
                    f"• شبكة النقل المختارة: `{network}`\n"
                    f"• رسوم الشبكة المضافة: `{network_fee}` USDT\n"
                    f"• عمولة البوت الثابتة: `{my_commission}` ليرة سورية\n"
                    f"• سعر الصرف المعتمد: `{rate}` ليرة لكل دولار\n\n"
                    f"💰 **المبلغ الكلي المطلوب تحويله بالليرة السورية:**\n"
                    f"👉 **{int(total_sp_cost):,} SP**\n\n"
                    f"📥 يرجى تحويل المبلغ الكلي بالليرة السورية إلى حسابنا (شام كاش):\n"
                    f"`{MY_WALLETS['SHAM_CASH']}`\n\n"
                    f"📸 بعد التحويل، أرسل لقطة شاشة الوصل (Screenshot) هنا فوراً لتأكيد طلبك وتلقي الرصيد."
                )
            else: # العميل يبيع USDT
                total_sp_receive = (amount * rate) - my_commission
                summary_text = (
                    f"📊 **تفاصيل عملية بيع USDT واستلام ليرة سورية:**\n\n"
                    f"• الكمية التي سترسلها لنا: `{amount}` USDT\n"
                    f"• شبكة النقل المختارة: `{network}`\n"
                    f"• عمولة البوت المخصومة: `{my_commission}` ليرة سورية\n"
                    f"• سعر الصرف المعتمد: `{rate}` ليرة لكل دولار\n\n"
                    f"💰 **المبلغ الكلي الذي ستستلمه بالليرة السورية:**\n"
                    f"👉 **{int(total_sp_receive):,} SP**\n\n"
                    f"📥 يرجى تحويل الـ `{amount}` USDT الصافية إلى عنوان محفظتنا التالي على شبكة **{network}**:\n"
                    f"`{MY_WALLETS[network]}`\n\n"
                    f"📸 بعد التحويل، أرسل لقطة شاشة الوصل (Screenshot) هنا فوراً مع كتابة حساب شام كاش الخاص بك لنحول لك الليرات السورية."
                )
            
            user_trade_steps[user_id]["amount"] = amount
            user_trade_steps[user_id]["total_sp"] = int(total_sp_cost if action == "buy" else total_sp_receive)
            user_trade_steps[user_id]["state"] = "WAIT_RECEIPT"
            
            bot.reply_to(message, summary_text, parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "⚠️ يرجى إدخال كمية صحيحة بالأرقام فقط (مثال: 100).")
        return

# 8. استقبال صور الإيصالات الحية وإرسالها للأدمن
@bot.message_handler(content_types=['photo'])
def receive_receipt_photo(message):
    user_id = str(message.from_user.id)
    
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_RECEIPT":
        bot.reply_to(message, "❤️ شكراً لك يا غالي، تم استقبال صورة إيصال التحويل بنجاح، وجاري مراجعتها وتدقيق الحساب حالياً من قبل الإدارة لتسليمك فوراً.")
        
        action = user_trade_steps[user_id]['action_raw'].upper()
        amount = user_trade_steps[user_id]['amount']
        network = user_trade_steps[user_id]['network']
        total_sp = user_trade_steps[user_id]['total_sp']
        
        try:
            caption_msg = (
                f"🚨 **إشعار عملية مالية وصرافة جديدة للمراجعة:**\n\n"
                f"• حساب العميل: `{user_id}`\n"
                f"• نوع العملية: **{action}** (USDT)\n"
                f"• شبكة التحويل: `{network}`\n"
                f"• كمية الدولار: `{amount}` USDT\n"
                f"• القيمة الإجمالية: **{total_sp:,} ليرة سورية**"
            )
            bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=caption_msg, parse_mode="Markdown")
        except Exception:
            pass
        del user_trade_steps[user_id]
    else:
        bot.reply_to(message, "❤️ تم استلام الصورة وتحويلها للإدارة لمراجعة رصيد شام كاش الخاص بك يدوياً وتثبيته.")
        try:
            bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=f"💰 **إيداع مباشر / شحن محفظة (شام كاش):**\n• حساب العميل: `{user_id}`")
        except Exception:
            pass

# 9. خادم ويب مدمج ومتوافق مع Render لضمان الاستقرار الحركي للبوت ومنع توقفه
async def handle_render_web_request(request):
    return web.Response(text="Syria Pure USDT Exchange Bot Is Fully Updated with correct BEP20 Wallet!")

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
