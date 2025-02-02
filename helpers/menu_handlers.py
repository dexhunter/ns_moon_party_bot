from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes
import asyncio
import base58
import logging

from helpers.wallet_tracker import start_periodic_task, get_wallet_balance  # Import the tracking function

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Shared user data
user_data = {}  # Stores data per user (chat_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Simply show the main menu without asking for a wallet address
    await show_main_menu(update, context)

# Update 'main_menu_handler' to call 'show_main_menu' when needed
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()

    # Initialize user data if it doesn't exist
    if chat_id not in user_data:
        user_data[chat_id] = {
            'tracked_wallets': [],
            'tasks': {},
            'last_transactions': {},
            'waiting_for_wallet': False
        }

    if query.data == 'add_wallet':
        # Set the flag to indicate the bot is waiting for wallet input
        user_data[chat_id]['waiting_for_wallet'] = True
        # Send a message asking for the wallet address and update the button to show "Waiting for Wallet..."
        keyboard = [
            [InlineKeyboardButton("Waiting for Wallet...", callback_data='add_wallet_waiting')],
            [InlineKeyboardButton("Cancel", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send the message and update the button
        await query.edit_message_text("Please send the wallet address and a name, separated by a space:", reply_markup=reply_markup)

    elif query.data == 'view_wallets':
        await view_wallets(update, context)

    elif query.data == 'start_tracking':
        await start_tracking(update, context)

    elif query.data == 'stop_tracking':
        await stop_tracking(update, context)

    elif query.data == 'back_to_main':
        # Reset the waiting flag when going back to the main menu
        user_data[chat_id]['waiting_for_wallet'] = False
        await show_main_menu(update, context)

# Add this function to check if the user is currently tracking
def is_tracking(chat_id):
    user = user_data.get(chat_id)
    return bool(user and user.get('tasks'))


# Modify the 'show_main_menu' function
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = user_data.get(chat_id)
    
    # Initialize user data if not present
    if user is None:
        user_data[chat_id] = {
            'tracked_wallets': [],
            'tasks': {},
            'last_transactions': {}
        }
        user = user_data[chat_id]

    # Check if the user is currently tracking any wallets
    tracking = is_tracking(chat_id)
    if tracking:
        tracking_button = [InlineKeyboardButton("Stop Tracking", callback_data='stop_tracking')]
    else:
        tracking_button = [InlineKeyboardButton("Start Tracking", callback_data='start_tracking')]

    # Create the menu buttons
    keyboard = [
        [InlineKeyboardButton("Add Wallet to Track", callback_data='add_wallet')],
        [InlineKeyboardButton("View Tracked Wallets", callback_data='view_wallets')],
        tracking_button
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        # Get the current message to avoid editing it with the same content
        current_message = update.callback_query.message.text
        new_message = "Please select an option:"
        
        # Only edit the message if the content has changed
        if current_message != new_message:
            await update.callback_query.edit_message_text(new_message, reply_markup=reply_markup)
        else:
            # Just update the buttons (reply_markup) if the text is the same
            await update.callback_query.edit_message_reply_markup(reply_markup=reply_markup)
    else:
        if update.message:
            await update.message.reply_text("Please select an option:", reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Please select an option:", reply_markup=reply_markup)


async def receive_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user = user_data.get(chat_id, {})

    # Initialize user data if it doesn't exist
    if chat_id not in user_data:
        user_data[chat_id] = {
            'tracked_wallets': [],
            'tasks': {},
            'last_transactions': {},
            'waiting_for_wallet': False
        }
        user = user_data[chat_id]

    # Check if it's a private chat (not a group)
    if update.message.chat.type == 'private':
        # Check if the bot is waiting for wallet input
        if not user.get('waiting_for_wallet', False):
            # If not waiting for wallet input, ignore the message
            await update.message.reply_text("Please press 'Add Wallet to Track' before sending a wallet address.")
            return

    # Reset the flag as we are processing the wallet now
    user['waiting_for_wallet'] = False
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        await update.message.reply_text("Please send the wallet address followed by a name, separated by a space.")
        return
    wallet_address, wallet_name = parts
    
    logger.debug(f"Received wallet address: {wallet_address}")
    
    if is_valid_solana_address(wallet_address):
        logger.debug("Wallet address is valid")
        if any(wallet['address'] == wallet_address for wallet in user['tracked_wallets']):
            escaped_wallet_name = escape_markdown(wallet_name, version=2)
            message = f"Wallet `{escaped_wallet_name}` is already in your tracking list\\."
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            user['tracked_wallets'].append({
                'address': wallet_address,
                'name': wallet_name,
                'checked': False
            })
            escaped_wallet_name = escape_markdown(wallet_name, version=2)
            message = f"Wallet `{escaped_wallet_name}` added to tracking list\\."
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            await view_wallets(update, context)
    else:
        logger.debug("Wallet address is invalid")
        await update.message.reply_text("Invalid wallet address. Please try again.")

def is_valid_solana_address(address: str) -> bool:
    try:
        # Decode the base58 address
        decoded = base58.b58decode(address)
        # Check if the decoded address is 32 bytes long
        is_valid = len(decoded) == 32
        logger.debug(f"Address validation result: {is_valid}")
        return is_valid
    except Exception as e:
        logger.error(f"Error validating address: {str(e)}")
        return False

# Modify 'view_wallets' to display wallet names with checkmarks
async def view_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        query = update.callback_query
        chat_id = update.effective_chat.id
    else:
        chat_id = update.message.chat_id  # Fallback if it's called from a regular message
        
    user = user_data.get(chat_id)
    
    if not user['tracked_wallets']:
        await context.bot.send_message(chat_id=chat_id, text="Please add a wallet first.")
        return

    keyboard = []
    wallet_info = []

    for wallet in user['tracked_wallets']:
        name = wallet['name']
        address = wallet['address']
        checked = wallet.get('checked', False)
        
        # Get the wallet balance
        balance = await get_wallet_balance(address)
        balance_str = f"{balance:.4f} SOL" if balance is not None else "Error"

        label = f"{name} {'✅' if checked else ''}"
        callback_data = f'toggle_wallet_{address}'
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
        
        wallet_info.append(f"{name}: {balance_str}")

    keyboard.append([InlineKeyboardButton("Back", callback_data='back_to_main')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Create the message with wallet information
    message = "Tracked Wallets (click to select):\n\n" + "\n".join(wallet_info)

    if update.callback_query:
        await query.edit_message_text(message, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup)
    
# Add a new handler 'toggle_wallet' to select a wallet to track
async def toggle_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    wallet_address = query.data.split('_')[-1]
    user = user_data.get(chat_id)
    selected_wallet = None
    # Uncheck all wallets and find the selected one
    # Mark the selected wallet as checked and uncheck the others
    for wallet in user['tracked_wallets']:
        if wallet['address'] == wallet_address:
            wallet['checked'] = True  # Set the selected wallet as checked
        else:
            wallet['checked'] = False  # Uncheck all others

    # Update the view to show the checked wallet but don't start tracking
    await view_wallets(update, context)
    
    
# Callback handler for removing a wallet
async def remove_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    wallet_to_remove = query.data.split('_')[-1]
    user = user_data.get(chat_id)
    if wallet_to_remove in user['tracked_wallets']:
        user['tracked_wallets'].remove(wallet_to_remove)
        # Also cancel any tracking tasks for this wallet
        task = user['tasks'].get(wallet_to_remove)
        if task:
            task.cancel()
            del user['tasks'][wallet_to_remove]
        await query.edit_message_text(f"Wallet `{wallet_to_remove}` removed from tracking list.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.edit_message_text("Wallet not found in your tracking list.")
    # Show updated wallet list
    await view_wallets(update, context)
    
    
async def start_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = update.effective_chat.id
    user = user_data.get(chat_id)
    
    if not user['tracked_wallets']:
        # Send a message to prompt the user to add a wallet
        await context.bot.send_message(chat_id=chat_id, text="Please add a wallet first.")
        # Redirect the user to the main menu to add a wallet
        await show_main_menu(update, context)
        return
        
    # Find the checked wallet
    selected_wallet = next((w for w in user['tracked_wallets'] if w.get('checked')), None)
    if not selected_wallet:
        # Send the message as a new message instead of editing the query message
        await context.bot.send_message(chat_id=chat_id, text="Please select a wallet to track from the 'View Tracked Wallets' menu.")
        # Redirect the user to the 'View Tracked Wallets' menu instead of leaving them stuck
        await view_wallets(update, context)
        return
    # Cancel all tracking tasks
    for task in user['tasks'].values():
        task.cancel()
    user['tasks'] = {}
    # Start tracking the selected wallet
    task = asyncio.create_task(start_periodic_task(chat_id, context, selected_wallet['address'], user_data))
    user['tasks'][selected_wallet['address']] = task
    
   # Log that tracking has started in the terminal
    #print(f"Started tracking wallet: {selected_wallet['address']} (Name: {selected_wallet['name']})")
    
    
    # Send the confirmation message (don't edit the menu message)
    await context.bot.send_message(chat_id=chat_id, text=f"Started tracking wallet `{escape_markdown(selected_wallet['name'], version=2)}`\\.", parse_mode=ParseMode.MARKDOWN_V2)
    
    # Show main menu again, which will now show "Stop Tracking"
    await show_main_menu(update, context)

async def stop_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = update.effective_chat.id
    user = user_data.get(chat_id)
    
    # Cancel all tracking tasks
    for task in user['tasks'].values():
        task.cancel()
    user['tasks'] = {}
    
    # Send the message saying tracking has stopped
    await context.bot.send_message(chat_id=chat_id, text="Stopped tracking your wallets.")
    
    # Update the inline keyboard to change the "Stop Tracking" button to "Start Tracking"
    keyboard = [
        [InlineKeyboardButton("Add Wallet to Track", callback_data='add_wallet')],
        [InlineKeyboardButton("View Tracked Wallets", callback_data='view_wallets')],
        [InlineKeyboardButton("Start Tracking", callback_data='start_tracking')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Update the reply_markup of the current menu without editing the message text
    await query.edit_message_reply_markup(reply_markup=reply_markup)


# Function to show tracking menu
async def show_tracking_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Stop Tracking", callback_data='stop_tracking')],
        [InlineKeyboardButton("Back to Main Menu", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Tracking in progress...", reply_markup=reply_markup)
    
   


# Update 'back_to_main_menu' to use 'show_main_menu'
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_main_menu(update, context)
    
# ... [Include other handler functions like view_wallets, toggle_wallet, start_tracking, stop_tracking, etc.]

# Don't forget to pass user_data to functions where needed

async def track_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = user_data.get(chat_id, {'tracked_wallets': []})
    
    logger.debug(f"Received track command: {update.message.text}")
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Please provide a wallet address and a name. Usage: /track <wallet_address> <wallet_name>")
        return

    wallet_address = context.args[0]
    wallet_name = ' '.join(context.args[1:])  # Join all remaining words as the wallet name
    
    logger.debug(f"Parsed wallet address: {wallet_address}")
    logger.debug(f"Parsed wallet name: {wallet_name}")

    if is_valid_solana_address(wallet_address):
        if any(wallet['address'] == wallet_address for wallet in user['tracked_wallets']):
            await update.message.reply_text(f"Wallet {wallet_address} is already being tracked.")
            return

        user['tracked_wallets'].append({
            'address': wallet_address,
            'name': wallet_name,
            'checked': False
        })
        user_data[chat_id] = user

        escaped_wallet_name = escape_markdown(wallet_name, version=2)
        escaped_wallet_address = escape_markdown(wallet_address, version=2)
        message = f"Wallet `{escaped_wallet_name}` with address `{escaped_wallet_address}` added to tracking list\\."
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        logger.debug(f"Invalid wallet address: {wallet_address}")
        await update.message.reply_text("Invalid wallet address. Please try again.")

def is_valid_solana_address(address: str) -> bool:
    try:
        # Decode the base58 address
        decoded = base58.b58decode(address)
        # Check if the decoded address is 32 bytes long
        is_valid = len(decoded) == 32
        logger.debug(f"Address validation result: {is_valid}")
        return is_valid
    except Exception as e:
        logger.error(f"Error validating address: {str(e)}")
        return False

async def list_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = user_data.get(chat_id, {'tracked_wallets': []})

    if not user['tracked_wallets']:
        await update.message.reply_text("No wallets are currently being tracked.")
        return

    if context.args:
        # List specific wallet
        wallet_address = context.args[0]
        wallet = next((w for w in user['tracked_wallets'] if w['address'] == wallet_address), None)
        if wallet:
            balance = await get_wallet_balance(wallet_address)
            balance_str = f"{balance:.4f} SOL" if balance is not None else "Error fetching balance"
            await update.message.reply_text(f"Wallet: {wallet['name']}\nAddress: {wallet['address']}\nBalance: {balance_str}")
        else:
            await update.message.reply_text(f"Wallet {wallet_address} is not being tracked.")
    else:
        # List all wallets
        message = "Tracked Wallets:\n\n"
        for wallet in user['tracked_wallets']:
            balance = await get_wallet_balance(wallet['address'])
            balance_str = f"{balance:.4f} SOL" if balance is not None else "Error fetching balance"
            message += f"Name: {wallet['name']}\nAddress: {wallet['address']}\nBalance: {balance_str}\n\n"
        await update.message.reply_text(message)

async def delete_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = user_data.get(chat_id, {'tracked_wallets': []})
    
    if not context.args:
        await update.message.reply_text("Please provide a wallet address or name to delete. Usage: /del <wallet_address_or_name>")
        return

    wallet_identifier = ' '.join(context.args)  # Join all args in case it's a multi-word name
    
    # Find the wallet to delete
    wallet_to_delete = next((w for w in user['tracked_wallets'] if w['address'] == wallet_identifier or w['name'].lower() == wallet_identifier.lower()), None)
    
    if not wallet_to_delete:
        await update.message.reply_text(f"No wallet found with address or name: {wallet_identifier}")
        return

    # Remove the wallet
    user['tracked_wallets'].remove(wallet_to_delete)
    
    # Cancel any tracking tasks for this wallet
    task = user['tasks'].get(wallet_to_delete['address'])
    if task:
        task.cancel()
        del user['tasks'][wallet_to_delete['address']]

    escaped_wallet_name = escape_markdown(wallet_to_delete['name'], version=2)
    escaped_wallet_address = escape_markdown(wallet_to_delete['address'], version=2)
    message = f"Wallet `{escaped_wallet_name}` with address `{escaped_wallet_address}` has been removed from the tracking list\\."
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
