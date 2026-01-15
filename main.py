import os
import logging
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
import requests
import time
import json

load_dotenv()

# Grizzly SMS Config
GRIZZLY_API_KEY = os.getenv("GRIZZLY_API_KEY")
GRIZZLY_BASE = "https://api.grizzlysms.com/stubs/handler_api.php"

# Telegram Bot Token
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Conversation states
SERVICE, COUNTRY, PRICE, CONFIRM = range(4)

# Popular services (code: display name)
SERVICES = {
    "fb": "Facebook",
    "wa": "WhatsApp",
    "tg": "Telegram",
    "go": "Google/Gmail",
    "ig": "Instagram",
}

# Simple country mapping (code: name + flag)
COUNTRIES = {
    "0": "🇷🇺 Russia",
    "1": "🇺🇦 Ukraine",
    "12": "🇺🇸 USA",
    "16": "🇮🇳 India",
    "9": "🇬🇧 UK",
    # လိုအပ်သလို ထပ်ထည့်ပါ
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def grizzly_request(action, params=None):
    if params is None:
        params = {}
    params["api_key"] = GRIZZLY_API_KEY
    params["action"] = action
    try:
        r = requests.get(GRIZZLY_BASE, params=params, timeout=12)
        r.raise_for_status()
        return r.text.strip()
    except Exception as e:
        logger.error(f"Grizzly error: {e}")
        return f"ERROR: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(name)] for name in SERVICES.values()]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Grizzly SMS Bot ကို ကြိုဆိုပါတယ်!\nဝန်ဆောင်မှု ရွေးပါ:",
        reply_markup=reply_markup
    )
    return SERVICE

async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    service_name = text
    service_code = next((k for k, v in SERVICES.items() if v == text), None)
    if not service_code:
        await update.message.reply_text("မမှန်ကန်တဲ့ ရွေးချယ်မှု။ /start နဲ့ ပြန်စပါ")
        return ConversationHandler.END

    context.user_data["service"] = service_code
    context.user_data["service_name"] = service_name

    # Get available countries (simple version)
    text = grizzly_request("getPricesV3", {"service": service_code})
    try:
        data = json.loads(text)
        avail_countries = []
        for c_code, svc in data.items():
            if service_code in svc and svc[service_code].get("count", 0) > 0:
                name = COUNTRIES.get(c_code, f"Country {c_code}")
                avail_countries.append((c_code, name))
    except:
        avail_countries = []

    if not avail_countries:
        await update.message.reply_text("ဒီ service အတွက် နိုင်ငံ မရှိပါ။")
        return ConversationHandler.END

    keyboard = [[KeyboardButton(name)] for _, name in avail_countries]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("နိုင်ငံ ရွေးပါ:", reply_markup=reply_markup)
    context.user_data["countries"] = avail_countries
    return COUNTRY

async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    countries = context.user_data.get("countries", [])
    selected = next((c for c_code, n in countries if n == text), None)
    if not selected:
        await update.message.reply_text("မမှန်ကန်ပါ။ /cancel နဲ့ ရပ်ပါ")
        return ConversationHandler.END

    c_code, c_name = selected
    context.user_data["country"] = c_code
    context.user_data["country_name"] = c_name

    # Prices (simple)
    prices_text = grizzly_request("getPricesV3", {"service": context.user_data["service"]})
    try:
        data = json.loads(prices_text)
        svc_data = data.get(c_code, {}).get(context.user_data["service"], {})
        price = svc_data.get("price", "N/A")
        count = svc_data.get("count", 0)
        price_str = f"${price} (available: {count})"
    except:
        price_str = "N/A"

    keyboard = [[KeyboardButton("ဝယ်မယ်")], [KeyboardButton("မဝယ်တော့ဘူး")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"{context.user_data['service_name']} - {c_name}\nPrice: {price_str}\n\nဝယ်မလား?",
        reply_markup=reply_markup
    )
    return CONFIRM

async def confirm_and_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "ဝယ်မယ်":
        await update.message.reply_text("Canceled. /start နဲ့ ပြန်စပါ")
        return ConversationHandler.END

    service = context.user_data["service"]
    country = context.user_data["country"]

    # Buy number
    resp = grizzly_request("getNumber", {"service": service, "country": country})
    if "ACCESS_NUMBER :" not in resp:
        await update.message.reply_text(f"Number မရပါ: {resp}")
        return ConversationHandler.END

    parts = resp.split(":", 2)
    act_id = parts[1].strip()
    phone = parts[2].strip()

    await update.message.reply_text(f"ရရှိတဲ့ နံပါတ်: {phone}\nID: {act_id}\n\nSMS စောင့်နေပါ...")

    # Wait for SMS (max 3 min)
    start_time = time.time()
    code = None
    while time.time() - start_time < 180:
        status = grizzly_request("getStatus", {"id": act_id})
        if "STATUS_OK:" in status:
            code = status.split(":", 1)[1].strip()
            grizzly_request("setStatus", {"id": act_id, "status": "6"})
            break
        if "STATUS_CANCEL" in status:
            break
        await asyncio.sleep(6)

    if code:
        await update.message.reply_text(f"Code ရပါပြီ: **{code}**")
    else:
        grizzly_request("setStatus", {"id": act_id, "status": "-1"})
        await update.message.reply_text("Code မရပါ။ Timeout / canceled")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Canceled.")
    return ConversationHandler.END

def main():
    if not TOKEN or not GRIZZLY_API_KEY:
        logger.error("Token or API key missing!")
        return

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_service)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_country)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_and_buy)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))

    print("Bot starting (webhook mode for Render)...")
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=TOKEN,
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}",
    )

if __name__ == "__main__":
    main()
