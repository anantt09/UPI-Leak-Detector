import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

load_dotenv()

# Database credentials
DB_HOST = "localhost"
DB_USER = "postgres"
DB_PASS = "root"  # Change if you have a different password
DB_NAME = "upitracker"

def init_database():
    try:
        # Connect to default postgres DB first to create the target DB if it doesn't exist
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database="postgres"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Check if database exists
        cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{DB_NAME}'")
        exists = cur.fetchone()
        
        if not exists:
            print(f"Database '{DB_NAME}' does not exist. Creating...")
            cur.execute(f"CREATE DATABASE {DB_NAME}")
            print(f"Database '{DB_NAME}' created successfully.")
        else:
            print(f"Database '{DB_NAME}' already exists.")
            
        cur.close()
        conn.close()
        
        # Now connect to the upitracker DB to create tables
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME
        )
        cur = conn.cursor()
        
        # Create users table with monthly_budget
        print("Creating 'users' table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                password_hash VARCHAR(128) NOT NULL,
                monthly_budget DECIMAL(10, 2) DEFAULT 0.00
            );
        """)
        
        # Create bank_accounts table
        print("Creating 'bank_accounts' table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bank_accounts (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                bank_name VARCHAR(100) NOT NULL,
                account_no VARCHAR(100) NOT NULL,
                current_balance DECIMAL(15, 2) NOT NULL,
                last_updated DATE NOT NULL,
                PRIMARY KEY (user_id, bank_name, account_no)
            );
        """)
        
        # Create transactions table with all columns used in app.py
        print("Creating 'transactions' table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                amount DECIMAL(10, 2) NOT NULL,
                date DATE NOT NULL,
                merchant VARCHAR(255) NOT NULL,
                category VARCHAR(100) NOT NULL,
                bank_name VARCHAR(100) DEFAULT 'Generic',
                account_no VARCHAR(100) DEFAULT 'Unknown'
            );
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database schema initialized successfully!")
        
    except Exception as e:
        print("Error initializing database:", e)
        print("\nPlease make sure PostgreSQL is running on localhost, and the credentials (user/password) in init_db.py match yours.")

if __name__ == "__main__":
    init_database()
