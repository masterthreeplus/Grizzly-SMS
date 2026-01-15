import os
import logging
import json
import time
import asyncio
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("GRIZZLY_API_KEY")
BASE_URL = "https://api.grizzlysms.com/stubs/handler_api.php"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States
SERVICE, COUNTRY, PRICE, CONFIRM = range(4)

# Popular services (display name → service code)
POPULAR_SERVICES = {
    "Telegram": "tg",
    "WhatsApp": "wa",
    "Facebook": "fb",
    "Google": "go",
    "Tiktok": "tt",
    "Viber": "vi",
    "Steam": "st",
    "Discord": "ds",
    "Amazon": "am",
    "Openai": "op",
    "Shopee": "sp",
    "Lazada": "lz",
    "Netflix": "nf",
}

# Country mapping example (code → flag + name). လက်တွေ့မှာ getPricesV3 ကနေ dynamic ဆွဲသုံး
COUNTRY_FLAGS = {
    "0": "🇷🇺 Russia",
    "1": "🇺🇦 Ukraine",
    "12": "🇺🇸 USA",
    "16": "🇮🇳 India",
    "7": "🇵🇭 Philippines",
    "id": "🇮🇩 Indonesia",  # လိုအပ်ရင် ထပ်ထည့်ပါ
    # နောက်ထပ် လိုအပ်ရင် dashboard ကနေ ကြည့်ပြီး ထည့်ပါ
}

def grizzly_request(action, extra_params=None):
    params = {"api_key": API_KEY, "action": action}
    if extra_params:
        params.update(extra_params)
    try:
        r = requests.get(BASE_URL, params=params, timeout=15)
        r.raise_for_status()
        return r.text.strip()
    except Exception as e:
        logger.error(f"Grizzly error ({action}): {e}")
        return f"ERROR: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = []
    row = []
    for name in POPULAR_SERVICES:
        row.append(KeyboardButton(f"🔥 {name}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([KeyboardButton("See All Services ➡️")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(
        "🔥 Popular Services:\nဝန်ဆောင်မှု ရွေးပါ 👇",
        reply_markup=reply_markup
    )
    return SERVICE

async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.replace("🔥 ", "").strip()
    service_code = POPULAR_SERVICES.get(text)
    if not service_code:
        await update.message.reply_text("ရွေးချယ်မှု မမှန်ပါ။ /start နဲ့ ပြန်စပါ")
        return ConversationHandler.END

    context.user_data["service_name"] = text
    context.user_data["service"] = service_code

    # Get available countries & prices (getPricesV3)
    resp = grizzly_request("getPricesV3", {"service": service_code})
    if "ERROR" in resp:
        await update.message.reply_text(f"နိုင်ငံ စစ်ဆေးမရပါ: {resp}")
        return ConversationHandler.END

    try:
        data = json.loads(resp)
    except:
        await update.message.reply_text("နိုင်ငံ ဒေတာ မမှန်ပါ။")
        return ConversationHandler.END

    countries = []
    for c_code, svc_data in data.items():
        if service_code in svc_data and svc_data[service_code].get("count", 0) > 0:
            flag_name = COUNTRY_FLAGS.get(c_code, f"🌍 {c_code.upper()}")
            price = svc_data[service_code].get("price", 0)
            qty = svc_data[service_code]["count"]
            countries.append((c_code, f"{flag_name} - from {int(price)} Ks ({qty})"))

    if not countries:
        await update.message.reply_text("ဒီ service အတွက် နိုင်ငံ မရှိပါ။")
        return ConversationHandler.END

    keyboard = [[KeyboardButton(name)] for _, name in countries[:10]]
    keyboard.append([KeyboardButton("Next ➡️")])
    keyboard.append([KeyboardButton("⬅️ Back to Services")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("နိုင်ငံ ရွေးပါ:", reply_markup=reply_markup)
    context.user_data["countries"] = countries
    return COUNTRY

async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    countries = context.user_data.get("countries", [])
    selected = next((c for c_code, n in countries if n == text), None)
    if not selected:
        await update.message.reply_text("နိုင်ငံ မမှန်ပါ။ /cancel နဲ့ ရပ်ပါ")
        return ConversationHandler.END

    c_code, c_name = selected
    context.user_data["country"] = c_code
    context.user_data["country_name"] = c_name.replace(" - ", " ").split(" - ")[0]  # clean

    # Price tiers (simple: min price ကနေ စျေးအဆင့်ခွဲ သို့မဟုတ် fixed)
    # Grizzly မှာ price tiers ရှိရင် getPricesV3 ထဲက providers သုံး၊ မရှိရင် maxPrice နဲ့ စမ်း
    prices = [
        {"label": f"Standard - {int(svc_data.get('price', 0))} Ks", "max_price": svc_data.get("price", 0) + 5},
        # လိုအပ်ရင် ထပ်ခွဲပါ (low, medium, high)
    ]
    # ရိုးရှင်းအောင် တစ်ခုတည်း သုံးမယ် (လက်တွေ့မှာ ချိန်ညှိ)
    keyboard = [[KeyboardButton("Buy Now - Any Price")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"{context.user_data['service_name']} - {context.user_data['country_name']}\n"
        f"စျေးနှုန်း ရွေးပါ (ရိုးရှင်းအောင် auto):",
        reply_markup=reply_markup
    )
    return CONFIRM

async def confirm_and_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if "Buy Now" not in update.message.text:
        await update.message.reply_text("Canceled. /start နဲ့ ပြန်စပါ")
        return ConversationHandler.END

    service = context.user_data["service"]
    country = context.user_data["country"]

    # Buy number (maxPrice optional)
    resp = grizzly_request("getNumber", {"service": service, "country": country})
    if not resp.startswith("ACCESS_NUMBER :"):
        await update.message.reply_text(f"Number မရပါ: {resp}")
        return ConversationHandler.END

    parts = resp.split(":", 2)
    act_id = parts[1].strip()
    phone = parts[2].strip()

    deducted = 500  # လက်တွေ့မှာ getPricesV3 ကနေ ယူပါ (placeholder)
    await update.message.reply_text(
        f"✅ Order Completed!\n"
        f"📱 Phone: {phone}\n"
        f"🌍 Country: {context.user_data['country_name']}\n"
        f"💸 Deducted: {deducted} Ks\n"
        f"📩 SMS စောင့်နေပါ..."
    )

    # Poll for SMS (max 3 min)
    start_time = time.time()
    code = None
    while time.time() - start_time < 180:
        status = grizzly_request("getStatus", {"id": act_id})
        if "STATUS_OK:" in status:
            code = status.split(":", 1)[1].strip()
            grizzly_request("setStatus", {"id": act_id, "status": "6"})  # complete
            break
        if "STATUS_CANCEL" in status:
            break
        await asyncio.sleep(6)

    if code:
        await update.message.reply_text(
            f"📩 SMS RECEIVED!\n"
            f"Code: {code}\n"
            f"Msg: (full message လိုရင် status ကနေ ယူ၊ ဒီမှာ placeholder)"
        )
    else:
        grizzly_request("setStatus", {"id": act_id, "status": "-1"})
        await update.message.reply_text("SMS မရပါ။ Timeout / canceled")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Canceled.")
    return ConversationHandler.END

def main():
    if not TOKEN or not API_KEY:
        logger.error("Token or API key missing!")
        return

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_service)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_country)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_and_buy)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    # Webhook for Render
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", "8443")),
        url_path=TOKEN,
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'your-app.onrender.com')}/{TOKEN}",
    )

if __name__ == "__main__":
    main()