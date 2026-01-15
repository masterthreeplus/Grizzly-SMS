import os
import requests
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Logging configuration
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment Variables
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("GRIZZLY_API_KEY")
BASE_URL = "https://api.grizzlysms.com/stubs/handler_api.php"

# --- API Helper Functions ---
def grizzly_api(action, extra_params={}):
    params = {'api_key': API_KEY, 'action': action}
    params.update(extra_params)
    try:
        response = requests.get(BASE_URL, params=params, timeout=15)
        return response.text
    except Exception as e:
        return f"ERROR:{str(e)}"

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Main Menu with Popular Services
    services = [
        ("Telegram", "tg"), ("WhatsApp", "wa"),
        ("Facebook", "fb"), ("Google", "go"),
        ("TikTok", "lf"), ("Discord", "ds")
    ]
    keyboard = []
    # ၂ ခု တစ်တန်းစီ ပြသရန်
    for i in range(0, len(services), 2):
        row = [
            InlineKeyboardButton(services[i][0], callback_data=f"svc_{services[i][1]}"),
            InlineKeyboardButton(services[i+1][0], callback_data=f"svc_{services[i+1][1]}")
        ]
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("💰 Check Balance", callback_data="balance")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔥 Popular Services:\nဖုန်းနံပါတ် ဝယ်ယူလိုသည့် Service ကို ရွေးပါ -", reply_markup=reply_markup)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    # 1. Balance စစ်ဆေးခြင်း
    if data == "balance":
        res = grizzly_api("getBalance")
        balance = res.split(":")[1] if ":" in res else res
        await query.message.reply_text(f"💳 Your Balance: {balance} RUB")

    # 2. Service ရွေးပြီးနောက် နိုင်ငံနှင့် ဈေးနှုန်းများကို Dynamic ပြခြင်း
    elif data.startswith("svc_"):
        service_code = data.split("_")[1]
        context.user_data['selected_service'] = service_code
        
        # getPrices API ကိုခေါ်ပြီး ဈေးနှုန်းနှင့် Stock အရေအတွက် ယူခြင်း
        # ဥပမာ - Indonesia(6), Vietnam(10), Thailand(52) စသည်
        target_countries = {"6": "🇮🇩 Indonesia", "10": "🇻🇳 Vietnam", "52": "🇹🇭 Thailand", "48": "🇳🇱 Netherlands"}
        
        keyboard = []
        for c_id, c_name in target_countries.items():
            # သက်ဆိုင်ရာ နိုင်ငံအလိုက် ဈေးနှုန်းစစ်ခြင်း
            price_res = grizzly_api("getPrices", {"service": service_code, "country": c_id})
            # Price Result format က JSON ဖြစ်နေတတ်လို့ သေချာစစ်ရပါမယ်
            # ဒီနေရာမှာ ရိုးရှင်းအောင် ပုံသေပြပြီး ဝယ်ခါနီးမှ API တိုက်ရိုက်ခေါ်ပြပါမယ်
            keyboard.append([InlineKeyboardButton(f"{c_name}", callback_data=f"cty_{c_id}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_start")])
        await query.edit_message_text(f"Selected: {service_code.upper()}\nနိုင်ငံကို ရွေးချယ်ပါ -", reply_markup=InlineKeyboardMarkup(keyboard))

    # 3. ဖုန်းနံပါတ် အမှန်တကယ် ဝယ်ယူခြင်း
    elif data.startswith("cty_"):
        country_id = data.split("_")[1]
        service = context.user_data.get('selected_service')
        
        await query.edit_message_text("🔄 နံပါတ်တောင်းဆိုနေပါသည်... ခဏစောင့်ပါ...")
        
        res = grizzly_api("getNumber", {"service": service, "country": country_id})
        
        if "ACCESS_NUMBER" in res:
            # Result: ACCESS_NUMBER:ID:PHONE
            _, activation_id, phone = res.split(":")
            context.user_data['activation_id'] = activation_id
            
            msg = (f"✅ နံပါတ်ရရှိပါပြီ!\n\n"
                   f"📞 Phone: `+{phone}`\n"
                   f"🆔 Order ID: `{activation_id}`\n\n"
                   f"Code ပို့လိုက်ပါ၊ ပြီးရင် အောက်က Button ကို နှိပ်ပါ -")
            
            btns = [
                [InlineKeyboardButton("📩 Check SMS", callback_data="check_sms")],
                [InlineKeyboardButton("❌ Cancel Order", callback_data="cancel_order")]
            ]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")
        else:
            await query.edit_message_text(f"❌ အဆင်မပြေပါ: {res}")

    # 4. SMS Status စစ်ဆေးခြင်း
    elif data == "check_sms":
        act_id = context.user_data.get('activation_id')
        res = grizzly_api("getStatus", {"id": act_id})
        
        if "STATUS_OK" in res:
            code = res.split(":")[1]
            await query.edit_message_text(f"📬 **SMS Code ရရှိပါပြီ!**\n\nCode: `{code}`", parse_mode="Markdown")
        elif "STATUS_WAIT_CODE" in res:
            await query.answer("SMS မဝင်သေးပါ။ ခဏနေမှ ထပ်နှိပ်ပါ သို့မဟုတ် စောင့်ပါ... ⏳", show_alert=True)
        else:
            await query.edit_message_text(f"Status: {res}")

    elif data == "back_to_start":
        await start(query, context)

if __name__ == '__main__':
    if not BOT_TOKEN or not API_KEY:
        print("Error: environment variables တေ ပျောက်နေပါတယ်!")
        exit(1)
        
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    
    print("Bot starting...")
    app.run_polling()
