import logging
import os
import threading
import sqlite3
import telebot
from telebot import types
from aiohttp import web
import asyncio

# 1. إعداد نظام تسجيل السجلات التقنية (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 2. البيانات الأساسية والمحافظ الثابتة للمؤسسة 🔐 (مراجعة ومطابقة 100%)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8859151257:AAF0SivQS_NiDcPaYiZFrt1p0Ep_T13lJTw")
ADMIN_CHAT_ID = "926536751"  # معرّف التلغرام الخاص بك المعتمد للإدارة

SUPPORT_LINK = "https://t.me/Syrusdt"  # رابط الدعم الفني الرسمي للمراسلة الفورية

MY_WALLETS = {
    "SHAM_CASH": "7a93267a0832f55f8b35abeaf28f8960",
    "BEP20": "0x6567Dc3Dad88274B121d651679778C0aB9f87804",
    "TON_USDT": "UQDbXMU9L45iztaFrwQdXMMqd6pMjsDPma4Jba_pWTRnSfEa",
    "TRON_TRX": "TKDPfmurDu9x7MgWPNUAa9i12wD5Enaw1B"
}

bot = telebot.TeleBot(BOT_TOKEN)

# هياكل البيانات المؤقتة لإدارة الجلسات والتذاكر
user_trade_steps = {}
admin_responses = {}

# 3. تهيئة وتحديث قاعدة البيانات المحلية (SQLite)
def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS blacklist (user_id TEXT PRIMARY KEY)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY)')
    
    # الإعدادات المالية والتنظيمية الافتراضية
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('usdt_buy_rate', '15000')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('usdt_sell_rate', '15500')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('combined_fee_rate', '2.5')") 
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('bot_status', 'ON')") 
    
    # تحديث آيدي الأدمن تلقائياً لضمان الصلاحيات الفورية ومنع التعليق
    cursor.execute("INSERT OR REPLACE INTO settings VALUES ('admin_id', ?)", (ADMIN_CHAT_ID,))
    
    conn.commit()
    conn.close()

def log_user(user_id):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

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

def is_blacklisted(user_id):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM blacklist WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def add_to_blacklist(user_id):
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO blacklist VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

# 4. لوحة تحكم الإدارة الحصرية (/admin)
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    init_db()
    if str(message.from_user.id) != ADMIN_CHAT_ID:
        bot.reply_to(message, "❌ خطأ في الصلاحية: هذا الأمر مخصص حصرياً للإدارة المخولة.")
        return
        
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 تعديل سعر الشراء", callback_data="adm_set_buy"),
        types.InlineKeyboardButton("📊 تعديل سعر المبيع", callback_data="adm_set_sell"),
        types.InlineKeyboardButton("⚙️ تعديل الرسوم المدمجة %", callback_data="adm_set_fee"),
        types.InlineKeyboardButton("📢 إرسال رسالة جماعية", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("🟢 وضع النشاط", callback_data="adm_status_ON"),
        types.InlineKeyboardButton("🟡 وضع الاستراحة", callback_data="adm_status_REST"),
        types.InlineKeyboardButton("🔴 وضع الإغلاق", callback_data="adm_status_OFF")
    )
    
    status_mapping = {"ON": "نشط وعامل 🟢", "REST": "في استراحة مؤقتة 🟡", "OFF": "خارج أوقات العمل 🔴"}
    current_status = status_mapping.get(get_setting("bot_status"), "غير محدد")
    
    info_text = (
        f"💼 **لوحة التحكم الإدارية والنظام المالي:**\n\n"
        f"• حالة النظام الحالية: {current_status}\n"
        f"• سعر شراء USDT الحالي: `{get_setting('usdt_buy_rate')}` ل.س\n"
        f"• سعر مبيع USDT الحالي: `{get_setting('usdt_sell_rate')}` ل.س\n"
        f"• الرسوم المدمجة للبيع: `{get_setting('combined_fee_rate')}` %\n\n"
        f"يرجى تحديد البند المطلوب لتعديل القيم نصياً:"
    )
    bot.send_message(message.chat.id, info_text, parse_mode="Markdown", reply_markup=markup)

# 5. واجهة التشغيل الرئيسية للمستخدمين (/start)
@bot.message_handler(commands=['start'])
def send_welcome(message):
    init_db()
    user_id = str(message.from_user.id)
    log_user(user_id)
    
    if is_blacklisted(user_id):
        bot.reply_to(message, "❌ تم تعليق صلاحية الوصول الخاصة بك إلى هذا النظام. يرجى مراجعة القسم المختص.")
        return
        
    if user_id in user_trade_steps: 
        del user_trade_steps[user_id]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔄 قسم المبادلة والصرافة الآلية", callback_data="usr_trade_main"),
        types.InlineKeyboardButton("📞 مركز الدعم الفني والاستفسارات", callback_data="usr_support_main")
    )
    
    bot.send_message(
        message.chat.id, 
        f"مرحباً بك {message.from_user.first_name} في المنصة الرسمية لخدمات الصرافة والتحويل المالي الذكي.\nيرجى تحديد نوع المعاملة المطلوبة من القائمة أدناه:", 
        reply_markup=markup
    )

# 6. معالجة طلبات الأزرار والتحكم التفاعلي (Callback Queries)
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = str(call.from_user.id)
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    if call.data.startswith("adm_") and user_id == ADMIN_CHAT_ID:
        if call.data == "adm_broadcast":
            user_trade_steps[user_id] = {"state": "WAIT_BROADCAST_MSG"}
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="📢 **قسم الإذاعة الجماعية:**\n\nيرجى إرسال نص الرسالة المراد تعميمها على كافة مستخدمي البوت حالياً:")
            return
        elif call.data.startswith("adm_set_"):
            setting_type = call.data.split("_")[2]
            user_trade_steps[user_id] = {"state": f"EDIT_{setting_type.upper()}"}
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="📥 يرجى إرسال القيمة الرقمية الجديدة عبر الحقل النصي مباشرة:")
            return
        elif call.data.startswith("adm_status_"):
            new_status = call.data.split("_")[2]
            update_setting("bot_status", new_status)
            bot.answer_callback_query(call.id, "✅ تم تحديث حالة النظام بنجاح.")
            admin_panel(call.message)
            return

    bot_status = get_setting("bot_status")
    if user_id != ADMIN_CHAT_ID and call.data.startswith("usr_"):
        if bot_status == "OFF":
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="🌙 أوقات سعيدة. المنصة مغلقة حالياً لانتهاء ساعات العمل الرسمية. نسعد بخدمتكم فور بدء النوبة التشغيلية القادمة. شكراً لتفهمكم.")
            return
        elif bot_status == "REST" and "trade" in call.data:
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔄 إعادة تشغيل النظام", callback_data="usr_restart"))
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="☕️ مرحباً بك. الإدارة حالياً في استراحة مؤقتة لتجديد الطاقة. يمكنك حساب أسعار الصرف حالياً، وسنكون على استعداد تام لاستلام الوصل وتنفيذ المعاملة خلال دقائق معدودة. شكراً لانتظاركم الموقر.", reply_markup=markup)
            return

    if call.data == "usr_restart":
        try: bot.delete_message(chat_id, msg_id)
        except: pass
        send_welcome(call.message)
        return

    if call.data == "usr_trade_main":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📥 شراء USDT من المنصة", callback_data="usr_action_buy"),
            types.InlineKeyboardButton("📤 بيع USDT إلى المنصة", callback_data="usr_action_sell")
        )
        markup.add(
            types.InlineKeyboardButton("🔙 رجوع", callback_data="usr_restart"),
            types.InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="usr_restart")
        )
        
        buy_rate = get_setting("usdt_buy_rate")
        sell_rate = get_setting("usdt_sell_rate")
        
        info_text = (
            f"📊 **نشرة أسعار الصرف الرسمية المعتمدة حالياً:**\n\n"
            f"• شراء المنصة للـ USDT (من العميل): `{buy_rate}` ل.س\n"
            f"• مبيع المنصة للـ USDT (إلى العميل): `{sell_rate}` ل.س\n\n"
            f"يرجى تحديد طبيعة المعاملة المالية للبدء في إجراءات التدقيق:"
        )
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=info_text, parse_mode="Markdown", reply_markup=markup)
        return

    if call.data.startswith("usr_action_"):
        action = call.data.split("_")[2]
        user_trade_steps[user_id] = {"action": action}
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🌐 شبكة BEP20", callback_data="usr_net_BEP20"),
            types.InlineKeyboardButton("🌐 شبكة TON USDT", callback_data="usr_net_TON_USDT"),
            types.InlineKeyboardButton("🌐 شبكة TRON TRX", callback_data="usr_net_TRON_TRX")
        )
        markup.add(
            types.InlineKeyboardButton("🔙 رجوع", callback_data="usr_trade_main"),
            types.InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="usr_restart")
        )
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="⚙️ يرجى تحديد شبكة وقناة النقل الرقمي المطلوبة لمتابعة احتساب الرسوم بدقة:", reply_markup=markup)
        return

    if call.data.startswith("usr_net_"):
        network = call.data.replace("usr_net_", "")
        if user_id in user_trade_steps:
            user_trade_steps[user_id]["network"] = network
            user_trade_steps[user_id]["state"] = "WAIT_AMOUNT"
            
            markup = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔙 رجوع", callback_data=f"usr_action_{user_trade_steps[user_id]['action']}"),
                types.InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="usr_restart")
            )
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="🔢 يرجى إدخال الكمية المالية المطلوبة بعملة الـ **USDT** (أرقام فقط، مثال: 50):", parse_mode="Markdown", reply_markup=markup)
        return

    if call.data == "usr_support_main":
        user_trade_steps[user_id] = {"state": "WAIT_SUPPORT_MSG"}
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💬 تواصل مباشر عبر التلغرام", url=SUPPORT_LINK),
            types.InlineKeyboardButton("🔙 رجوع", callback_data="usr_restart"),
            types.InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="usr_restart")
        )
        
        support_text = (
            f"📞 **مركز خدمات وتذاكر الدعم الفني المباشر:**\n\n"
            f"• المعرّف الخاص بحسابكم الموقر (ID): `{user_id}`\n"
            f"• حساب التلغرام الرسمي للمراسلة الفورية: @Syrusdt\n\n"
            f"يمكنك الضغط على زر التواصل المباشر في الأسفل للمراسلة الفورية، أو كتابة استفسارك هنا نصياً ليتم فتح تذكرة دعم فني داخل البوت فوراً."
        )
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=support_text, parse_mode="Markdown", reply_markup=markup)
        return

    if call.data.startswith("adm_decision_") and user_id == ADMIN_CHAT_ID:
        parts = call.data.split("_")
        decision = parts[2]
        target_user_id = parts[3]
        
        if decision == "approve":
            approve_text = (
                f"🎉 **إشعار مالي رسمي:**\n\n"
                f"تم التحقق من لقطة شاشة الإيصال المالي الخاص بكم، وقبول الطلب بنجاح من قبل الإدارة الموقرة.\n\n"
                f"📥 **الخطوة الإلزامية التالية:**\n"
                f"يرجى إرسال (عنوان حساب شام كاش الخاص بكم) نصياً في حقل الكتابة فوراً، ليتمكن القسم المالي من إتمام عملية تحويل مستحقاتكم المالية دون تأخير."
            )
            bot.send_message(target_user_id, approve_text, parse_mode="Markdown")
            bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=f"✅ تم قبول المعاملة المالية للمستخدم `{target_user_id}` وإخطاره بطلب حساب شام كاش.")
        
        elif decision == "reject":
            admin_responses[ADMIN_CHAT_ID] = {"action": "WAIT_REJECT_REASON", "target_user": target_user_id, "original_msg_id": msg_id}
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ يرجى كتابة (سبب الرفض المالي والمعلل) للمستخدم `{target_user_id}` نصياً الآن لإرساله إليه:")
        return

    if call.data.startswith("adm_sup_") and user_id == ADMIN_CHAT_ID:
        action = call.data.split("_")[2]
        target_user_id = call.data.split("_")[3]
        
        if action == "reply":
            admin_responses[ADMIN_CHAT_ID] = {"action": "WAIT_SUPPORT_REPLY", "target_user": target_user_id}
            bot.send_message(ADMIN_CHAT_ID, f"💬 يرجى كتابة نص الرد الموجه للمستخدم `{target_user_id}` حالياً:")
        elif action == "block":
            add_to_blacklist(target_user_id)
            bot.send_message(ADMIN_CHAT_ID, f"🚫 تم إدراج المستخدم `{target_user_id}` في القائمة السوداء، وتم حظر وصوله للنظام نهائياً.")
        return

# 7. معالجة وحساب العمليات المالية والرسائل النصية المباشرة
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = str(message.from_user.id)
    text = message.text.strip()
    
    if user_id == ADMIN_CHAT_ID:
        if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_BROADCAST_MSG":
            all_users = get_all_users()
            sent_count = 0
            for u in all_users:
                try:
                    bot.send_message(u, f"📢 **إعلان رسمي هام من إدارة المنصة:**\n\n{text}", parse_mode="Markdown")
                    sent_count += 1
                except: pass
            bot.reply_to(message, f"✅ تم انتهاء البث بنجاح، وتم تسليم الإشعار المالي إلى `{sent_count}` مستخدم نشط حالياً دفعة واحدة.")
            del user_trade_steps[user_id]
            return

        if user_id in user_trade_steps and str(user_trade_steps[user_id].get("state", "")).startswith("EDIT_"):
            state = user_trade_steps[user_id]["state"]
            key_mapping = {"EDIT_BUY": "usdt_buy_rate", "EDIT_SELL": "usdt_sell_rate", "EDIT_FEE": "combined_fee_rate"}
            if state in key_mapping:
                update_setting(key_mapping[state], text)
                bot.reply_to(message, "✅ تم تحديث النظام المالي والبيانات بنجاح في قاعدة البيانات المحلية.")
            del user_trade_steps[user_id]
            return
            
        if user_id in admin_responses:
            adm_action = admin_responses[user_id]["action"]
            target = admin_responses[user_id]["target_user"]
            
            if adm_action == "WAIT_REJECT_REASON":
                reject_msg = (
                    f"❌ **إشعار رفض المعاملة المالية:**\n\n"
                    f"نأسف لإخطاركم برفض إيصال التحويل المالي من قبل قسم التدقيق والمطابقة.\n"
                    f"📌 **السبب المعلن:** {text}\n\n"
                    f"يرجى مراجعة وتعديل البيانات المعاملاتية والمحاولة مرة أخرى بدقة."
                )
                bot.send_message(target, reject_msg, parse_mode="Markdown")
                bot.send_message(ADMIN_CHAT_ID, f"✅ تم إرسال سبب الرفض بنجاح إلى المستخدم `{target}`.")
                try: bot.delete_message(message.chat.id, admin_responses[user_id]["original_msg_id"])
                except: pass
                del admin_responses[user_id]
                return
                
            elif adm_action == "WAIT_SUPPORT_REPLY":
                reply_msg = f"📩 **رد رسمي من الدعم الفني للمنصة:**\n\n{text}"
                bot.send_message(target, reply_msg, parse_mode="Markdown")
                bot.send_message(ADMIN_CHAT_ID, f"✅ تم تسليم الرد الرسمي للمستخدم `{target}`.")
                del admin_responses[user_id]
                return

    if is_blacklisted(user_id):
        return

    if text.isalnum() and len(text) > 20 and user_id not in user_trade_steps:
        wait_text = (
            "✅ **إشعار منظومة الصرف:**\n\n"
            "مرحباً بك. تم **تسجيل** وتوثيق حساب شام كاش الخاص بكم بنجاح، وتوجيه الأمر المالي المباشر إلى قسم الحوالات الخارجية والصرف.\n\n"
            "⏳ يرجى الانتظار لعدة دقائق، حيث يتم حالياً معالجة الطلب وإتمام عملية التحويل المالي إلى حسابكم الموقر دون أي تأخير. شكراً لثقتكم الكريمة."
        )
        bot.reply_to(message, wait_text, parse_mode="Markdown")
        notification = (
            f"🏦 **إشعار تسليم حساب تحويل (شام كاش):**\n\n"
            f"• معرّف العميل المالي (ID): `{user_id}`\n"
            f"• حساب شام كاش المستهدف للتحويل:\n`{text}`\n\n"
            f"يرجى مراجعة الحساب والتحويل الفوري وإغلاق التذكرة المالية."
        )
        bot.send_message(ADMIN_CHAT_ID, notification, parse_mode="Markdown")
        return

    # مسار استلام محفظة استلام الـ USDT الموجهة من العميل في خطوة الشراء النهائية قبل إرسال الوصل
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_BUY_WALLET":
        user_trade_steps[user_id]["user_wallet"] = text
        user_trade_steps[user_id]["state"] = "WAIT_RECEIPT"
        
        # [تعديل هام 🛑]: إضافة التحذير الصارم بخصوص كتابة الملاحظات أو الرموز في إشعار شام كاش
        buy_text = (
            f"📥 **تم تسجيل عنوان محفظة الاستلام الخاصة بكم بنجاح:**\n`{text}`\n\n"
            f"📌 **الخطوة الأخيرة لإتمام المعاملة:**\n"
            f"يرجى الآن تحويل القيمة الإجمالية المطلوبة بالليرة السورية إلى حساب شام كاش الموحد للمؤسسة التالي:\n"
            f"`{MY_WALLETS['SHAM_CASH']}`\n\n"
            f"⚠️ **تحذير أمني وقانوني صارم جداً 🛑:**\n"
            f"يجب أن يكون التحويل **بدون أي رموز أو كتابة ملاحظات** في حقل الملاحظات الخاص بإشعار التحويل نهائياً.\n"
            f"**إذا تضمن إشعار التحويل أي كتابة أو ملاحظة ستفشل العملية تلقائياً وسيتم رفض الطلب.**\n\n"
            f"بعد إتمام التحويل، يرجى إرسال ملف الإيصال المالي كـ **صورة حية (Screenshot)** حصرياً هنا للمطابقة الفورية والتدقيق والتحقق من سلامة الحوالة."
        )
        bot.send_message(message.chat.id, buy_text, parse_mode="Markdown")
        return

    # حاسبة التدفق المالي والكميات المحددة من العملاء
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_AMOUNT":
        try:
            amount = float(text)
            action = user_trade_steps[user_id]["action"]
            network = user_trade_steps[user_id]["network"]
            
            if amount < 2.0:
                markup = types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🔙 رجوع", callback_data=f"usr_net_{network}"),
                    types.InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="usr_restart")
                )
                bot.reply_to(message, "❌ **خطأ تنظيمي:** الحد الأدنى المسموح به لإجراء عمليات البيع أو المبادلة عبر المنصة هو **2$ USDT** فقط كحد أدنى. يرجى إدخال قيمة مطابقة.", reply_markup=markup)
                return
                
            rate = float(get_setting("usdt_sell_rate" if action == "buy" else "usdt_buy_rate"))
            fee_rate = float(get_setting("combined_fee_rate"))
            
            if action == "buy":
                total_sp_cost = amount * rate
                summary_text = (
                    f"📋 **الفاتورة المالية المبدئية - أمر شراء USDT:**\n\n"
                    f"• الكمية المستهدفة الصافية: `{amount}` USDT\n"
                    f"• شبكة وقناة الاستلام الرقمية: `{network}`\n"
                    f"• سعر صرف مبيع الـ USDT الحالي: `{rate}` ل.س لكل دولار\n\n"
                    f"💰 **المبلغ الإجمالي المستحق سداده بالليرة السورية:**\n"
                    f"👉 **{int(total_sp_cost):,} ل.س**\n\n"
                    f"📥 **إجراء إجباري حاسم:**\n"
                    f"يرجى إرسال **عنوان محفظتك الشخصية الصالحة** التابعة لشبكة **({network})** نصياً في حقل الكتابة أدناه الآن.\n\n"
                    f"⚠️ **تنبيه أمني بالغ الأهمية:**\n"
                    f"تأكد تماماً من مطابقة الشبكة وصلاحية العنوان، المنصة تخلي مسؤوليتها الكاملة عن إرسال العملات لعناوين خاطئة أو شبكات غير مطابقة من قِبلك."
                )
                user_trade_steps[user_id]["amount"] = amount
                user_trade_steps[user_id]["total_sp"] = int(total_sp_cost)
                user_trade_steps[user_id]["state"] = "WAIT_BUY_WALLET"
                
            else:
                gross_sp = amount * rate
                fee_deduction = gross_sp * (fee_rate / 100.0)
                total_sp_receive = gross_sp - fee_deduction
                
                summary_text = (
                    f"📋 **الفاتورة المالية المبدئية - أمر بيع USDT:**\n\n"
                    f"• الكمية الرقمية المراد إرسالها: `{amount}` USDT\n"
                    f"• شبكة النقل الرقمية المختارة: `{network}`\n"
                    f"• سعر صرف الشراء المعتمد: `{rate}` ل.س لكل دولار\n"
                    f"• الرسوم المدمجة المخصومة (الشبكة + المنصة %): `{fee_rate}` %\n\n"
                    f"💰 **المبلغ الإجمالي الصافي الذي ستستلمه بالليرة السورية:**\n"
                    f"👉 **{int(total_sp_receive):,} ل.س**\n\n"
                    f"📥 **عنوان محفظة الإيداع الرسمية التابعة للمنصة:**\n"
                    f"يرجى تحويل الكمية الصافية بدقة إلى عنوان شبكة **{network}** التالي:\n`{MY_WALLETS[network]}`\n\n"
                    f"⚠️ **تحذير أمني وقانوني صارم:**\n"
                    f"تأكد تماماً من مطابقة شبكة النقل المختارة والمبلغ بدقة قبل تفعيل الأمر. بعد إتمام التحويل الرقمي، يرجى إرسال ملف الإشعار المالي كـ **صورة حية (Screenshot)** حصرياً هنا للتدقيق المالي والتسليم. إرسال بيانات مكتوبة يتسبب في رفض المعاملة وتجميد الصلاحيات."
                )
                user_trade_steps[user_id]["amount"] = amount
                user_trade_steps[user_id]["total_sp"] = int(total_sp_receive)
                user_trade_steps[user_id]["state"] = "WAIT_RECEIPT"
                
            markup = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔙 رجوع وتغيير القيمة", callback_data=f"usr_net_{network}"),
                types.InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="usr_restart")
            )
            bot.send_message(message.chat.id, summary_text, parse_mode="Markdown", reply_markup=markup)
        except ValueError:
            bot.reply_to(message, "❌ **خطأ في الصياغة:** يرجى إدخال قيم وكميات رقمية صحيحة وصالحة فقط (مثال: 100).")
        return

    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_SUPPORT_MSG":
        bot.reply_to(message, "✅ تم تسجيل وتوجيه تذكرة الدعم الفني بنجاح إلى القسم الإداري المختص، وسيتم مراجعتها والرد الرسمي المباشر عليها عبر هذا الحقل الموحد.")
        
        adm_markup = types.InlineKeyboardMarkup(row_width=2)
        adm_markup.add(
            types.InlineKeyboardButton("💬 الرد الرسمي", callback_data=f"adm_sup_reply_{user_id}"),
            types.InlineKeyboardButton("🚫 حظر العميل", callback_data=f"adm_sup_block_{user_id}")
        )
        
        notification_text = (
            f"📩 **تذكرة دعم فني جديدة واردة للمراجعة:**\n\n"
            f"• معرّف حساب العميل (ID): `{user_id}`\n"
            f"• نص الرسالة والاستفسار الوارد:\n{text}"
        )
        bot.send_message(ADMIN_CHAT_ID, notification_text, parse_mode="Markdown", reply_markup=adm_markup)
        del user_trade_steps[user_id]
        return

    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_RECEIPT":
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔄 إعادة محاولة إرسال الوصل كصورة", callback_data="usr_restart"))
        bot.reply_to(message, "❌ **خطأ في المطابقة الأمنية:** تم رفض البيانات المكتوبة. يرجى إرسال ملف الإيصال المالي المباشر كـ **صورة حية (Screenshot)** حصرياً لكي يتمكن النظام الحسابي من فحص المعاملة وتوثيقها.", reply_markup=markup)

# 8. استقبال إيصالات الدفع (الصور الحية حصرياً وحظر الغش)
@bot.message_handler(content_types=['photo'])
def receive_receipt_photo(message):
    user_id = str(message.from_user.id)
    if is_blacklisted(user_id):
        return
        
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_RECEIPT":
        wait_msg = (
            "✅ **إشعار منظومة الصرف والتدقيق:**\n\n"
            "مرحباً بك. تم **تسجيل** وتوثيق وثيقة الإيصال المالي الخاص بكم بنجاح، وتوجيه المعاملة مباشرة إلى قسم المطابقة الحسابية الخارجي.\n\n"
            "⏳ يرجى الانتظار لعدة دقائق، حيث يتم حالياً فحص التذكرة المالية وإنهاء عملية تحويل مستحقاتكم دون أي تأخير. شكراً لثقتكم الموقرة وجاري المعالجة."
        )
        bot.reply_to(message, wait_msg, parse_mode="Markdown")
        
        action = user_trade_steps[user_id]['action'].upper()
        amount = user_trade_steps[user_id]['amount']
        network = user_trade_steps[user_id]['network']
        total_sp = user_trade_steps[user_id]['total_sp']
        user_wallet = user_trade_steps[user_id].get('user_wallet', 'مذكور في الخطوة التالية أو حوالة مباشرة لشام كاش')
        
        adm_markup = types.InlineKeyboardMarkup(row_width=2)
        adm_markup.add(
            types.InlineKeyboardButton("✅ قبول واعتماد الطلب", callback_data=f"adm_decision_approve_{user_id}"),
            types.InlineKeyboardButton("❌ رفض الطلب ماليًا", callback_data=f"adm_decision_reject_{user_id}")
        )
        
        caption_msg = (
            f"🚨 **إشعار معاملة مالية جديدة واردة وبانتظار قرار الإدارة:**\n\n"
            f"• معرّف حساب العميل المالي: `{user_id}`\n"
            f"• طبيعة ونوع المعاملة: **{action}** (USDT)\n"
            f"• شبكة النقل المالي المعتمدة: `{network}`\n"
            f"• كمية الأصول الرقمية المحددة: `{amount}` USDT\n"
            f"• القيمة الإجمالية المقدرة بالعملة المحلية: **{total_sp:,} ل.س**\n"
            f"• محفظة العميل الشخصية المستهدفة (في حال الشراء): `{user_wallet}`\n"
            f"⚠️ تأكد من خلو إشعار الشام كاش من أي كتابة أو رموز قبل القبول!"
        )
        try:
            bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=caption_msg, parse_mode="Markdown", reply_markup=adm_markup)
        except Exception as e:
            logger.error(f"Failed to forward photo to admin: {e}")
        del user_trade_steps[user_id]
    else:
        bot.reply_to(message, "📥 تم استلام لقطة الشاشة وتوجيه التذكرة إلى قسم الإيداعات للمراجعة وتثبيت رصيد شام كاش الخاص بكم يدوياً.")
        try:
            bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=f"🏦 **طلب إيداع وحوالة مباشرة واردة (شام كاش):**\n• معرّف العميل المالي (ID): `{user_id}`")
        except Exception as e:
            logger.error(f"Failed to forward generic photo to admin: {e}")

# 9. خادم ويب مدمج ومتوافق تقنياً مع بيئة خوادم Render لضمان الاستقرار الحركي للبوت ومنع توقفه
async def handle_render_web_request(request):
    return web.Response(text="Corporate Pure USDT Exchange Platform Is Active with Advanced Integrated Systems.")

def start_isolated_web_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = web.Application()
    app.router.add_get('/', handle_render_web_request)
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 10000)))
    loop.run_forever()

if __name__ == '__main__':
    init_db()
    threading.Thread(target=start_isolated_web_server, daemon=True).start()
    bot.infinity_polling()
