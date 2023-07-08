import psycopg2
from src.config import db_config

def connect_to_db():
    conn = psycopg2.connect(
        dbname=db_config.DB_NAME,
        host=db_config.DB_HOST,
        user=db_config.DB_USER,
        password=db_config.DB_PASSWORD
    )
    return conn