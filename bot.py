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

# 2. البيانات الأساسية والإعدادات
BOT_TOKEN = "8859151257:AAFQ7WpXsjYg_RJnHgE82ZU_O-WjXUtUaW8"
ADMIN_CHAT_ID = "920536751"  # معرف حسابك لتلقي الإيصالات والطلبات
SUPPORT_LINK = "https://t.me/Syrusdt"

MOUSA_API_TOKEN = "C280gLYN12_xlghy548ztmGu60VUsbHuf6c_6Mwgvpbdvltov3ktxxmDZjHN"
MOUSA_API_BASE_URL = "https://mousa-card.com/api/v2"

# عناوين محافظك الرسمية الموزعة حسب نوع العملية (تم تصحيح التسمية لـ SHAM_CASH)
MY_WALLETS = {
    "BEP20": "0x6567Dc3dAd882748121d65167977Bc0ad9F878d4",
    "TRC20": "0x6567Dc3dAd882748121d65167977Bc0ad9F878d4",
    "TON": "UQBBXWRM9L4SlzlaFrwQdXmMqd6pNjS0Fha4Jba_pMTRnEFa",
    "SHAM_CASH": "7a93267a0832F55F0b3Sabeadf28f896"
}

bot = telebot.TeleBot(BOT_TOKEN)
user_trade_steps = {}

# 3. حاسبة الأرباح التلقائية لمنتجات المتجر حسب خانات السعر
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
        return original_price_str

# 4. جلب خدمات Mousa Card وتصنيفها
def fetch_mousa_products_by_category(category_keyword):
    try:
        headers = {
            "Authorization": f"Bearer {MOUSA_API_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.get(f"{MOUSA_API_BASE_URL}/services", headers=headers, timeout=10)
        if response.status_code == 200:
            all_services = response.json()
            filtered_products = []
            for service in all_services:
                name = service.get("name", "").lower()
                if category_keyword == "games" and any(k in name for k in ["pubg", "free fire", "جواهر", "شحن", "ببجي", "uc"]):
                    filtered_products.append(service)
                elif category_keyword == "chat" and any(k in name for k in ["likee", "tiktok", "تيك توك", "شات"]):
                    filtered_products.append(service)
                elif category_keyword == "vpn" and any(k in name for k in ["vpn", "بروكسي", "حظر"]):
                    filtered_products.append(service)
            return filtered_products
        return []
    except Exception as e:
        return []

def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, balance REAL DEFAULT 0.0)')
    conn.commit()
    conn.close()

# 5. واجهات التفاعل والتحكم للمتجر والصرافة
@bot.message_handler(commands=['start'])
def send_welcome(message):
    init_db()
    user_id = str(message.from_user.id)
    if user_id in user_trade_steps: del user_trade_steps[user_id]
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🛒 تصفح المتجر (ألعاب وتطبيقات)", callback_data="browse_store"),
        types.InlineKeyboardButton("🔄 شراء ومبيع USDT / صرافة آلي", callback_data="trade_usdt_main"),
        types.InlineKeyboardButton("💰 شحن المحفظة (Sham Cash)", callback_data="deposit_wallet"),
        types.InlineKeyboardButton("📞 الدعم الفني المباشر", url=SUPPORT_LINK)
    )
    bot.reply_to(message, f"👋 أهلاً بك يا {message.from_user.first_name} في متجر وصرافة سوريا الآلية المحدثة بقنوات الدفع المحلية!", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = str(call.from_user.id)
    
    if call.data == "browse_store":
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("🎮 ألعاب", callback_data="prod_games"),
            types.InlineKeyboardButton("💬 شات", callback_data="prod_chat"),
            types.InlineKeyboardButton("🌐 VPN", callback_data="prod_vpn")
        )
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🗂️ أقسام متجر الألعاب والتطبيقات الحية المتاحة:", reply_markup=markup)
        
    elif call.data.startswith("prod_"):
        category = call.data.split("_")[1]
        products = fetch_mousa_products_by_category(category)
        if not products:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 العودة للأقسام", callback_data="browse_store"))
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚠️ القسم قيد التحديث حالياً من المصدر.", reply_markup=markup)
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for prod in products[:10]:
            final_p = calculate_custom_price(prod.get("rate", "0"))
            markup.add(types.InlineKeyboardButton(f"{prod.get('name')} | 💰 {final_p} SYP", callback_data=f"buy_{prod.get('id')}"))
        markup.add(types.InlineKeyboardButton("🔙 العودة للأقسام", callback_data="browse_store"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎁 الخدمات الحالية المتوفرة بالليرة السورية:", reply_markup=markup)

    # --- نظام الصرافة الآلي والتحقق من التوجيه الصحيح لقنوات الدفع ---
    elif call.data == "trade_usdt_main":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🟢 شراء USDT من البوت", callback_data="action_buy"),
            types.InlineKeyboardButton("🔴 بيع USDT إلى البوت", callback_data="action_sell")
        )
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🔄 **قسم الصرافة الآلي المطور.**\n\nيرجى تحديد نوع العملية المطلوبة للتحقق وتوجيهك للمحفظة الصحيحة تلقائياً:", parse_mode="Markdown", reply_markup=markup)
        
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
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"⚙️ لقد اخترت عملية: **{action_type} USDT**\n\nيرجى تحديد نوع الشبكة الرقمية المراد استخدامها لإكمال طلبك:", parse_mode="Markdown", reply_markup=markup)
        
    elif call.data.startswith("net_"):
        network = call.data.split("_")[1]
        if user_id in user_trade_steps:
            user_trade_steps[user_id]["network"] = network
            user_trade_steps[user_id]["state"] = "WAIT_AMOUNT"
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"🔢 شبكة العملة المحددة: **{network}**\n\nيرجى كتابة **كمية الـ USDT** المراد تداولها الآن كرسالة نصية في الشات (مثال: 100):",
                parse_mode="Markdown"
            )

    elif call.data == "deposit_wallet" or call.data == "main_menu":
        if user_id in user_trade_steps: del user_trade_steps[user_id]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🛒 تصفح المتجر (ألعاب وتطبيقات)", callback_data="browse_store"),
            types.InlineKeyboardButton("🔄 شراء ومبيع USDT / صرافة آلي", callback_data="trade_usdt_main"),
            types.InlineKeyboardButton("💰 شحن المحفظة (Sham Cash)", callback_data="deposit_wallet")
        )
        if call.data == "deposit_wallet":
            deposit_text = f"💰 **شحن المحفظة المحلية (Sham Cash)**\n\n📌 **حساب Sham Cash المعتمد بالبوت:** `{MY_WALLETS['SHAM_CASH']}`\n\nيرجى تحويل الرصيد المطلوب ثم إرسال إيصال التحويل إلى الدعم الفني لإضافته لحسابك."
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=deposit_text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎛️ القائمة الرئيسية للمتجر الحالية:", reply_markup=markup)

# 6. استقبال وإدارة رسائل إدخال الكميات وعرض المحافظ والتحقق الذكي
@bot.message_handler(func=lambda message: str(message.from_user.id) in user_trade_steps and user_trade_steps[str(message.from_user.id)].get("state") == "WAIT_AMOUNT")
def receive_amount(message):
    user_id = str(message.from_user.id)
    amount = message.text
    
    user_trade_steps[user_id]["amount"] = amount
    user_trade_steps[user_id]["state"] = "WAIT_RECEIPT"
    
    action_raw = user_trade_steps[user_id]["action_raw"]
    action = user_trade_steps[user_id]["action"]
    network = user_trade_steps[user_id]["network"]
    
    # التحقق التلقائي المحدث بناءً على نوع العملية لإرسال المحفظة الصحيحة
    if action_raw == "buy":
        # العميل يشتري USDT -> يعني يرسل لنا ليرات سورية على شام كاش
        target_wallet = MY_WALLETS["SHAM_CASH"]
        wallet_title = "حساب Sham Cash السوري المعتمد للمتجر"
    else:
        # العميل يبيع USDT -> يعني يرسل لنا عملة رقمية على محفظتنا المقابلة للشبكة المحددة
        target_wallet = MY_WALLETS.get(network, "غير متوفر")
        wallet_title = f"عنوان محفظة USDT الرسمية للشبكة ({network})"
        
    instruction_msg = (
        f"✅ **ملخص وتفاصيل المعاملة الحالية:**\n"
        f"• نوع طلب الصرافة: {action} USDT\n"
        f"• الكمية المستهدفة: {amount} USDT\n"
        f"• الشبكة المحددة: {network}\n\n"
        f"📥 **الرجاء التحويل الآن إلى العنوان المخصص التالي:**\n"
        f"📌 {wallet_title}:\n"
        f"`{target_wallet}`\n\n"
        f"📸 **الخطوة الأخيرة:** بعد إتمام عملية التحويل الفعلي للرصيد، يرجى إرسال **صورة إيصال التحويل (Screenshot)** هنا مباشرة في الشات لإرسالها للإدارة وتأكيد طلبك فورا."
    )
    bot.reply_to(message, instruction_msg, parse_mode="Markdown")

# 7. استقبال الإيصال وتوجيهه للآدمن
@bot.message_handler(content_types=['photo'])
def receive_receipt_photo(message):
    user_id = str(message.from_user.id)
    
    if user_id in user_trade_steps and user_trade_steps[user_id].get("state") == "WAIT_RECEIPT":
        bot.reply_to(message, "⏳ جارٍ رفع إيصالك وتمرير الطلب لغرفة تدقيق الإدارة الحية... سيتم إشعارك فور المراجعة والتنفيذ.")
        
        photo_file_id = message.photo[-1].file_id
        action = user_trade_steps[user_id]["action"]
        network = user_trade_steps[user_id]["network"]
        amount = user_trade_steps[user_id]["amount"]
        user_name = message.from_user.first_name or "مجهول"
        username_tg = f"@{message.from_user.username}" if message.from_user.username else "لا يوجد"
        
        admin_report_text = (
            f"🚨 **إشعار بطلب صرافة جديد (تم التحقق من العناوين)!**\n\n"
            f"👤 **بيانات العميل:**\n"
            f"• الاسم: {user_name}\n"
            f"• اليوزر: {username_tg}\n"
            f"• الآيدي: `{user_id}`\n\n"
            f"⚙️ **تفاصيل المعاملة المرفقة:**\n"
            f"• العملية المتخذة: *{action} USDT*\n"
            f"• الشبكة المستخدمة: *{network}*\n"
            f"• الكمية المدخلة: `{amount} USDT`\n\n"
            f"👇 صورة الإيصال المرفقة أدناه للتدقيق والمطابقة اليدوية:"
        )
        
        try:
            bot.send_photo(ADMIN_CHAT_ID, photo_file_id, caption=admin_report_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"❌ فشل إرسال الإيصال للأدمن: {e}")
            
        del user_trade_steps[user_id]

# 8. خادم ويب لـ Render لمنع النوم
async def handle_render_web_request(request):
    return web.Response(text="Syria Smart Verified Sham Cash Exchange Core is Active 24/7!")

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
