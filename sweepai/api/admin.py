from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from .login import oauth2_scheme

router = APIRouter()

class Employee(BaseModel):
    name: str
    email: str
    role: str
    id: Optional[int] = None

employees = []

from jose import jwt, JWTError

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    return users.get(token_data.email)

@router.post("/employee")
def create_employee(employee: Employee, current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    employee.id = len(employees) + 1
    employees.append(employee)
    return employee

@router.get("/employee/{employee_id}")
def read_employee(employee_id: int, token: str = Depends(oauth2_scheme)):
    if token != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    for employee in employees:
        if employee.id == employee_id:
            return employee
    raise HTTPException(status_code=404, detail="Employee not found")

@router.put("/employee/{employee_id}")
def update_employee(employee_id: int, employee: Employee, token: str = Depends(oauth2_scheme)):
    if token != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    for index, existing_employee in enumerate(employees):
        if existing_employee.id == employee_id:
            employees[index] = employee
            return employee
    raise HTTPException(status_code=404, detail="Employee not found")

@router.delete("/employee/{employee_id}")
def delete_employee(employee_id: int, token: str = Depends(oauth2_scheme)):
    if token != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    for index, existing_employee in enumerate(employees):
        if existing_employee.id == employee_id:
            employees.pop(index)
            return {"message": "Employee deleted"}
    raise

