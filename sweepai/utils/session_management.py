import uuid

# Store the session data in a dictionary for simplicity
# In a real-world application, this data would likely be stored in a database or some other persistent storage
session_data = {}

def create_session(user_id):
    """Create a new session for a user."""
    # Generate a new session ID
    session_id = str(uuid.uuid4())
    
    # Store the session ID and user ID in the session data
    session_data[session_id] = user_id
    
    # Return the session ID
    return session_id

def check_session(session_id):
    """Check if a session is valid (i.e., exists in the session data)."""
    return session_id in session_data

def destroy_session(session_id):
    """Destroy a session (i.e., remove it from the session data)."""
    if session_id in session_data:
        del session_data[session_id]