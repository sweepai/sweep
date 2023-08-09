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
    # Hash the password before storing
    hashed_password = hash_password(password)
    user = User(username=username, password=hashed_password)

    # Save the user entity in the database
    user.save()

    return {"success": True, "message": "User registration successful"}