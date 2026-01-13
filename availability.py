import requests
from typing import List, Dict, Any
from datetime import datetime, timedelta
import os
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode


# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_available_seats(structure_id: str, date: str, time_slot: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get available seats for a specific time slot across all library rooms.
    
    Args:
        structure_id: The library structure ID (e.g., "4b867ddd-46fd-4fe5-a57b-cdd4a3e1520d")
        date: Date in format "YYYY-MM-DD" (e.g., "2026-01-13")
        time_slot: Time in format "HH:MM" (e.g., "13:00")
    
    Returns:
        Dictionary with room types as keys and lists of available seats as values
    """
    # Blacklisted resource types (Group study rooms, Faculty/PhD seats, Laptops)
    BLACKLIST = {1, 2860, 4415}
    
    # Headers to mimic a browser request
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    }
    
    # Get room types info
    infos_url = f"https://reservation.affluences.com/api/sites/{structure_id}/infos"
    infos_response = requests.get(infos_url, headers=headers)
    infos_response.raise_for_status()
    infos_data = infos_response.json()
    
    # Filter out blacklisted room types
    room_types = [
        room_type for room_type in infos_data.get("types", [])
        if room_type["resource_type"] not in BLACKLIST
    ]
    
    # Dictionary to store results by room type
    results = {}
    
    # For each room type, fetch available seats
    for room_type in room_types:
        resource_type = room_type["resource_type"]
        room_name = room_type["localized_description"]
        
        # Get available resources for this room type
        available_url = f"https://reservation.affluences.com/api/resources/{structure_id}/available"
        params = {
            "date": date,
            "type": resource_type
        }
        
        available_response = requests.get(available_url, headers=headers, params=params)
        available_response.raise_for_status()
        resources = available_response.json()
        
        # Filter resources that are available at the specified time slot
        available_seats = []
        for resource in resources:
            hours = resource.get("hours", [])
            
            # Find the index of the requested time slot
            time_slot_index = None
            for idx, hour_slot in enumerate(hours):
                if hour_slot["hour"] == time_slot:
                    time_slot_index = idx
                    break
            
            # If time slot found and available, calculate continuous availability
            if time_slot_index is not None and hours[time_slot_index]["state"] == "available":
                # Count consecutive available slots starting from the requested time
                consecutive_slots = 0
                for i in range(time_slot_index, len(hours)):
                    if hours[i]["state"] == "available":
                        consecutive_slots += 1
                    else:
                        break
                
                # Calculate duration (each slot is 30 minutes)
                duration_minutes = consecutive_slots * 30
                duration_hours = duration_minutes / 60
                
                # Get end time
                last_available_index = time_slot_index + consecutive_slots - 1
                end_time = hours[last_available_index]["hour"]
                
                available_seats.append({
                    "resource_id": resource["resource_id"],
                    "resource_name": resource["resource_name"],
                    "description": resource.get("description", ""),
                    "places_available": hours[time_slot_index]["places_available"],
                    "consecutive_slots": consecutive_slots,
                    "duration_minutes": duration_minutes,
                    "duration_hours": duration_hours,
                    "end_time": end_time
                })
        
        # Only add to results if there are available seats
        if available_seats:
            results[room_name] = available_seats
    
    return results


def format_results(results: Dict[str, List[Dict[str, Any]]], date: str, time_slot: str) -> str:
    """Format the results into a nice message"""
    if not results:
        return f"No available seats found for {date} at {time_slot} 😔"
    
    message = f"<b>📚 Available seats for {date} at {time_slot}</b>\n\n"
    
    total_seats = sum(len(seats) for seats in results.values())
    message += f"<b>Total: {total_seats} seats available</b>\n\n"
    
    for room_name, seats in results.items():
        # Sort seats by duration (longest first)
        seats_sorted = sorted(seats, key=lambda x: x['duration_minutes'], reverse=True)
        
        message += f"<b>{room_name}</b> ({len(seats)} seats)\n"
        
        # Show top 3 longest available seats for each room
        for seat in seats_sorted[:3]:
            duration_str = f"{seat['duration_hours']:.1f}h" if seat['duration_hours'] >= 1 else f"{seat['duration_minutes']}min"
            message += f"  • {seat['resource_name']}\n    Until {seat['end_time']} ({duration_str})\n"
        
        if len(seats_sorted) > 3:
            message += f"  ... and {len(seats_sorted) - 3} more\n"
        
        message += "\n"
    
    return message


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_msg = (
        "👋 Welcome to the Library Seat Finder Bot!\n\n"
        "Commands:\n"
        "/check - Check available seats now\n"
        "/check HH:MM - Check seats at specific time (e.g., /check 14:30)\n"
        "/check YYYY-MM-DD HH:MM - Check seats on specific date and time\n\n"
        "Example: /check 2026-01-15 15:00"
    )
    await update.message.reply_text(welcome_msg)


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /check command"""
    structure_id = context.bot_data.get('structure_id')
    
    # Default to current date and time
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    # Round to next 30-minute slot
    minutes = (now.minute // 30 + 1) * 30
    if minutes == 60:
        now = now + timedelta(hours=1)
        minutes = 0
    time_slot = f"{now.hour:02d}:{minutes:02d}"
    
    # Parse arguments
    args = context.args
    if len(args) == 1:
        # /check HH:MM
        time_slot = args[0]
    elif len(args) == 2:
        # /check YYYY-MM-DD HH:MM
        date = args[0]
        time_slot = args[1]
    
    # Validate format
    try:
        datetime.strptime(date, "%Y-%m-%d")
        datetime.strptime(time_slot, "%H:%M")
    except ValueError:
        await update.message.reply_text(
            "Invalid date or time format. Use:\n/check YYYY-MM-DD HH:MM"
        )
        return
    
    await update.message.reply_text(
        f"🔍 Searching for available seats...\nDate: {date}\nTime: {time_slot}"
    )
    
    try:
        results = get_available_seats(structure_id, date, time_slot)
        formatted_msg = format_results(results, date, time_slot)
        await update.message.reply_text(formatted_msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        await update.message.reply_text(f"Error fetching data: {str(e)}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Main function to run the bot"""
    # Get configuration from environment variables
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g., https://yourdomain.com/webhook
    PORT = int(os.environ.get("PORT", 8080))
    STRUCTURE_ID = os.environ.get("STRUCTURE_ID", "4b867ddd-46fd-4fe5-a57b-cdd4a3e1520d")
    
    if not BOT_TOKEN:
        logger.error("Error: Please set TELEGRAM_BOT_TOKEN environment variable")
        exit(1)
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Store structure_id in bot_data for access in handlers
    application.bot_data['structure_id'] = STRUCTURE_ID
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_error_handler(error_handler)
    
    if WEBHOOK_URL:
        # Run with webhook
        logger.info(f"Starting bot with webhook: {WEBHOOK_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=f"{WEBHOOK_URL}/webhook"
        )
    else:
        # Run with polling (for local development)
        logger.info("Starting bot with polling (local development mode)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
