from fastapi import Request, HTTPException
from sweepai.core.entities import User

async def register_user(request: Request):
    """Handle a user registration request."""
    # Extract user input from the request
    data = await request.json()
    username = data.get('username')
    password = data.get('password')

    # Validate user input
    if not username or not password:
        raise HTTPException(status_code=400, detail="Invalid input")

    # Create a new User entity
    # TODO: Hash the password before storing
    user = User(username=username, password=password)

    # TODO: Save the user entity in the database
    # TODO: Implement database saving functionality

    return {"success": True, "message": "User registration successful"}