import requests
from typing import List, Dict, Any


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


# Example usage
if __name__ == "__main__":
    structure_id = "4b867ddd-46fd-4fe5-a57b-cdd4a3e1520d"
    date = "2026-01-13"
    time_slot = "13:00"
    
    try:
        available_seats = get_available_seats(structure_id, date, time_slot)
        
        print(f"Available seats for {date} at {time_slot}:\n")
        
        if not available_seats:
            print("No available seats found.")
        else:
            for room_name, seats in available_seats.items():
                print(f"{room_name}: {len(seats)} seats available")
                
                # Sort seats by duration (longest first)
                seats_sorted = sorted(seats, key=lambda x: x['duration_minutes'], reverse=True)
                
                for seat in seats_sorted:
                    duration_str = f"{seat['duration_hours']:.1f}h" if seat['duration_hours'] >= 1 else f"{seat['duration_minutes']}min"
                    print(f"  - {seat['resource_name']} (available until {seat['end_time']}, {duration_str})")
                print()
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
