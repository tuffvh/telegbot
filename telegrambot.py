import io
import random
import string
import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ForceReply,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import requests
from flask import Flask
import threading

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8325392232:AAGsgBdi3B7HKjqhznSeunakvTPZv93aUhA"
BACKEND_URL = "https://percmenu.com/tgbot/"

user_data = {}

# --- Flask webserver for keep-alive ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()
# --- End Flask keep-alive ---


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"/start by {user.id} (@{user.username})")
    try:
        requests.post(
            BACKEND_URL + "register_user.php",
            data={"telegram_id": str(user.id), "username": user.username or user.full_name},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Error registering user {user.id}: {e}")

    keyboard = [
        [InlineKeyboardButton("➕ Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance")],
        [InlineKeyboardButton("🆔 Get My User ID", callback_data="get_user_id")],
        [InlineKeyboardButton("🧾 Buy Lines ($0.5 per line)", callback_data="buy_lines")],
        [InlineKeyboardButton("📦 Check Stock", callback_data="check_stock")],  # New button
    ]
    await update.message.reply_text(
        "Welcome to the CB Lines Bot", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    logger.info(f"Button clicked: {query.data} by {user_id}")
    await query.answer()

    if query.data == "add_balance":
        keyboard = [
            [InlineKeyboardButton("BTC", callback_data="coin_BTC")],
            [InlineKeyboardButton("ETH", callback_data="coin_ETH")],
            [InlineKeyboardButton("LTC", callback_data="coin_LTC")],
            [InlineKeyboardButton("SOL", callback_data="coin_SOL")],
            [InlineKeyboardButton("USDT", callback_data="coin_USDT")],
        ]
        await query.edit_message_text(
            "Choose a payment method:", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith("coin_"):
        coin = query.data.split("_")[1]
        user_data[user_id] = {"coin": coin}
        await query.edit_message_text(f"You selected {coin}.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Please send the amount you want to deposit (minimum $5):",
            reply_markup=ForceReply(selective=True),
        )

    elif query.data == "check_balance":
        try:
            resp = requests.post(
                BACKEND_URL + "get_balance.php", data={"telegram_id": user_id}, timeout=10
            )
            data = resp.json()
            balance = float(data.get("balance", 0))
        except Exception as e:
            logger.error(f"Error checking balance for {user_id}: {e}")
            balance = 0
        await query.edit_message_text(f"💳 Your current balance: ${balance:.2f}")

    elif query.data == "get_user_id":
        await query.edit_message_text(
            f"Your Telegram User ID is:\n`{user_id}`", parse_mode="Markdown"
        )

    elif query.data == "buy_lines":
        await query.edit_message_text(
            "How many lines do you want to buy? Each line costs $0.50."
        )
        user_data[user_id] = {"awaiting_quantity": True}

    elif query.data == "check_stock":  # New handler for stock check
        try:
            resp = requests.post(
                BACKEND_URL + "get_stock.php",  # You need this PHP to return JSON {"success":true, "stock":123}
                timeout=10,
            )
            data = resp.json()
            if data.get("success"):
                stock = data.get("stock", 0)
                await query.edit_message_text(f"📦 Current lines in stock: {stock}")
            else:
                await query.edit_message_text("❌ Failed to fetch stock info.")
        except Exception as e:
            logger.error(f"Error fetching stock info: {e}")
            await query.edit_message_text("❌ Error fetching stock info.")


async def amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()

    # Check if user is expected to send quantity for buying lines
    if user_id in user_data and user_data[user_id].get("awaiting_quantity"):
        try:
            quantity = int(text)
            if quantity < 1:
                raise ValueError("Quantity must be at least 1")
        except Exception:
            await update.message.reply_text(
                "Please enter a valid whole number greater than 0 for the quantity."
            )
            return

        logger.info(f"User {user_id} wants to buy {quantity} lines")
        try:
            resp = requests.post(
                BACKEND_URL + "buy_line.php",
                data={"telegram_id": user_id, "lines": quantity},
                timeout=10,
            )
            data = resp.json()
            if data.get("success"):
                new_balance = float(data.get("new_balance", 0))
                lines = data.get("lines", [])
                if lines:
                    # Prepare the file content
                    file_content = "\n\n".join(lines)
                    # Generate a random filename like Lines-XXXX-XXXX-XXXX.txt
                    def random_section(n=4):
                        return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))

                    filename = f"Lines-{random_section()}-{random_section()}-{random_section()}.txt"
                    file_bytes = io.BytesIO(file_content.encode("utf-8"))
                    file_bytes.name = filename

                    await update.message.reply_document(
                        document=InputFile(file_bytes),
                        caption=f"✅ Bought {quantity} line(s) for ${quantity * 0.5:.2f}\nNew balance: ${new_balance:.2f}"
                    )
                else:
                    await update.message.reply_text(
                        f"✅ Bought {quantity} line(s) for ${quantity * 0.5:.2f}\n"
                        f"New balance: ${new_balance:.2f}\n\nNo lines returned."
                    )
            else:
                await update.message.reply_text(
                    f"❌ Purchase failed: {data.get('message', 'Unknown error')}"
                )
        except Exception as e:
            logger.error(f"Error during purchase for {user_id}: {e}")
            await update.message.reply_text(f"❌ Error during purchase: {e}")

        user_data.pop(user_id, None)
        return

    # Handle deposit amount (if user is adding balance)
    if user_id not in user_data or "coin" not in user_data[user_id]:
        await update.message.reply_text("Please start with /start and choose Add Balance first.")
        return

    try:
        amount = float(text)
    except ValueError:
        await update.message.reply_text("Please send a valid number for amount.")
        return

    if amount < 5:
        await update.message.reply_text("Minimum deposit amount is $5. Please send a higher amount.")
        return

    coin = user_data[user_id]["coin"]
    try:
        resp = requests.post(
            BACKEND_URL + "create_invoice.php",
            data={"telegram_id": user_id, "amount": amount, "currency": coin},
            timeout=10,
        )
        data = resp.json()
        payment_url = (
            data.get("payment_url")
            or data.get("invoice_url")
            or data.get("payment_address")
            or data.get("pay_address")
        )
    except Exception as e:
        logger.error(f"Error creating invoice for {user_id}: {e}")
        payment_url = None

    if payment_url:
        await update.message.reply_text(
            f"Please complete your payment here:\n[Pay Now]({payment_url})",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("Failed to create payment invoice. Try again later.")

    user_data.pop(user_id, None)


def main():
    keep_alive()  # Start Flask keep-alive webserver in background

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, amount_handler))

    logger.info("Bot started successfully.")
    app.run_polling()


if __name__ == "__main__":
    main()
