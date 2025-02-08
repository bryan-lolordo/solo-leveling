import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establishes a connection to PostgreSQL."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Error connecting to PostgreSQL: {e}")
        return None

def insert_routine(user_id, date, wake_up_time, sleep_time, meal_times, workout, bad_habits, energy_level, stress_level):
    """Inserts a daily routine into the database."""
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        query = """
        INSERT INTO daily_routines (user_id, date, wake_up_time, sleep_time, meal_times, workout, bad_habits, energy_level, stress_level)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING routine_id;
        """
        cur.execute(query, (user_id, date, wake_up_time, sleep_time, meal_times, workout, bad_habits, energy_level, stress_level))
        routine_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Routine added with ID {routine_id}")

def fetch_routines(user_id):
    """Fetches all routines for a user."""
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        query = "SELECT * FROM daily_routines WHERE user_id = %s ORDER BY date DESC;"
        cur.execute(query, (user_id,))
        rows = cur.fetchall()
        print("📆 User's Daily Routines:")
        for row in rows:
            print(row)
        cur.close()
        conn.close()
        print("🔌 Connection closed")

if __name__ == "__main__":
    # Test inserting a routine
    insert_routine(
        user_id=1,
        date="2025-02-06",
        wake_up_time="10:00",
        sleep_time="02:00",
        meal_times=["10:20", "14:00", "19:00"],
        workout="15-minute walk",
        bad_habits=["Starbucks coffee and sandwich"],
        energy_level=5,
        stress_level=6
    )

    # Test fetching routines
    fetch_routines(user_id=1)
