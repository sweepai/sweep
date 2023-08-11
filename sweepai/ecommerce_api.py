from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

class Product(BaseModel):
    id: int
    name: str
    price: float

class Order(BaseModel):
    id: int
    user_id: int
    product_ids: List[int]

class User(BaseModel):
    id: int
    name: str
    email: str

products = []
orders = []
users = []

ecommerce_api = APIRouter()

@ecommerce_api.get("/products")
def get_products():
    return products

@ecommerce_api.post("/products")
def create_product(product: Product):
    products.append(product)
    return product

@ecommerce_api.get("/orders")
def get_orders():
    return orders

@ecommerce_api.post("/orders")
def create_order(order: Order):
    orders.append(order)
    return order

@ecommerce_api.get("/users")
def get_users():
    return users

@ecommerce_api.post("/users")
def create_user(user: User):
    users.append(user)
    return user