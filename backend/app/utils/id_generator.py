import uuid
import time

def generate_short_id() -> str:
    """
    Generates a short unique message ID.
    This creates a shorter ID than a full UUID while still being unique enough for our purposes.
    The format matches the frontend implementation for consistency.
    
    Returns:
        A short unique ID string (format: '8-char-uuid-segment-4-digit-timestamp')
    """
    # Generate a full UUID
    full_uuid = str(uuid.uuid4())
    
    # Take just the first segment of the UUID (8 chars)
    first_segment = full_uuid.split('-')[0]
    
    # Add a timestamp component for additional uniqueness (last 4 digits of current timestamp)
    timestamp_part = str(int(time.time() * 1000))[-4:]
    
    # Combine for a short but unique ID
    return f"{first_segment}-{timestamp_part}" 