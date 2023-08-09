from fastapi import Request, HTTPException
from sweepai.core.entities import User

async def authenticate_user(request: Request):
    """Handle a user authentication request."""
    # Extract user input from the request
    data = await request.json()
    username = data.get('username')
    password = data.get('password')

    # Validate user input
    if not username or not password:
        raise HTTPException(status_code=400, detail="Invalid input")

    # Check the User entities for a match
    user = User.get(username=username)
    if user is None or not user.check_password(password):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    # If a match is found, create a new session
    session_id = create_session(user.id)

    return {"success": True, "session_id": session_id}