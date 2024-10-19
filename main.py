import logging
import os
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from dotenv import load_dotenv
from helpers.menu_handlers import (
    start,
    show_main_menu,
    receive_wallet_address,
    main_menu_handler,
    remove_wallet,
    stop_tracking,
    toggle_wallet,
    back_to_main_menu,
    user_data,
    track_wallet,
    list_wallets,
    delete_wallet,  # New import
)
from telegram import Update
from telegram.ext import ContextTypes

# Load environment variables
load_dotenv()
# Get the TELEGRAM_TOKEN from the environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)

async def list_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    commands = [
        "/start - Start the bot and show the main menu",
        "/menu - Show the main menu",
        "/track <wallet_address> <wallet_name> - Add a new wallet to track",
        "/listall - List all tracked wallets",
        "/del <wallet_address_or_name> - Delete a tracked wallet",
        "/list - Show this list of commands"
    ]
    message = "Available commands:\n\n" + "\n".join(commands)
    await update.message.reply_text(message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.text and message.text.startswith('/'):
        # This is a command, so we should process it
        command = message.text.split()[0].lower()
        if command == '/track':
            await track_wallet(update, context)
        elif command == '/listall':
            await list_wallets(update, context)
        elif command == '/list':
            await list_commands(update, context)
        elif command == '/menu':
            await show_main_menu(update, context)
        elif command == '/del':
            await delete_wallet(update, context)
        # Add other commands as needed
    elif message.text and context.bot.username and f'@{context.bot.username}' in message.text:
        # The bot was tagged, but no specific command was given
        await message.reply_text("Hello! I'm here to help. Use /list to see available commands.")
    else:
        # The message doesn't contain a command and the bot wasn't tagged, so we ignore it
        return

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_main_menu))
    application.add_handler(CommandHandler("track", track_wallet))
    application.add_handler(CommandHandler("listall", list_wallets))
    application.add_handler(CommandHandler("list", list_commands))
    application.add_handler(CommandHandler("del", delete_wallet))  # New command handler

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(main_menu_handler, pattern='^(add_wallet|view_wallets|start_tracking|back_to_main)$'))
    application.add_handler(CallbackQueryHandler(remove_wallet, pattern='^remove_wallet_'))
    application.add_handler(CallbackQueryHandler(stop_tracking, pattern='^stop_tracking$'))
    application.add_handler(CallbackQueryHandler(toggle_wallet, pattern='^toggle_wallet_'))

    # Message handler for all text messages
    application.add_handler(MessageHandler(filters.TEXT, handle_message))

    application.run_polling()

if __name__ == '__main__':
    main()
