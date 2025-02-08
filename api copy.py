import os
import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware




# ✅ Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ Initialize FastAPI app
app = FastAPI()

# ✅ Enable CORS for React & Flutter UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to specific frontend domains later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Database connection function
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        return None

# ✅ Root endpoint for API test
@app.get("/")
async def root():
    return {"message": "Solo Leveling API is running!"}

# ✅ Habit Adjustment Endpoint (Now prevents duplicate suggestions)
@app.get("/adjust_habits/{user_id}")
async def adjust_habits(user_id: int):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()

        # Get existing pending suggestions
        cur.execute(
            "SELECT habit FROM habit_adjustments WHERE user_id = %s AND status = 'pending'", (user_id,)
        )
        existing_habits = {row[0] for row in cur.fetchall()}  # Set of pending habit names

        # Fetch latest routine
        cur.execute("""
            SELECT wake_up_time, sleep_time, meal_times, energy_level, stress_level, bad_habits, workout
            FROM daily_routines 
            WHERE user_id = %s 
            ORDER BY date DESC 
            LIMIT 1;
        """, (user_id,))
        
        routine = cur.fetchone()
        if not routine:
            return {"message": "❌ No routine data found for this user"}

        wake_up_time, sleep_time, meal_times, energy_level, stress_level, bad_habits, workout = routine
        adjustments = []

        # 🔹 Wake-Up Time Adjustment
        if "wake_up_time" not in existing_habits and sleep_time.hour > 1:
            new_wake_time = f"{max(6, wake_up_time.hour - 1):02d}:{wake_up_time.minute:02d}"
            adjustments.append({"habit": "wake_up_time", "suggested_change": new_wake_time})
            cur.execute("""
                INSERT INTO habit_adjustments (user_id, applied_on, current_value, next_suggested_value, reason, status, habit)
                VALUES (%s, CURRENT_DATE, %s, %s, %s, 'pending', %s)
            """, (user_id, wake_up_time, new_wake_time, "Gradual wake-up shift", "wake_up_time"))

        # 🔹 Sleep Time Adjustment
        if "sleep_time" not in existing_habits and sleep_time.hour > 1:
            new_sleep_time = f"{max(22, sleep_time.hour - 1):02d}:{sleep_time.minute:02d}"
            adjustments.append({"habit": "sleep_time", "suggested_change": new_sleep_time})
            cur.execute("""
                INSERT INTO habit_adjustments (user_id, applied_on, current_value, next_suggested_value, reason, status, habit)
                VALUES (%s, CURRENT_DATE, %s, %s, %s, 'pending', %s)
            """, (user_id, sleep_time, new_sleep_time, "Improve sleep quality", "sleep_time"))

        # 🔹 Meal Timing Adjustment
        if "meal_times" not in existing_habits and isinstance(meal_times, list):
            new_meal_times = []
            for time in meal_times:
                h, m = map(int, time.split(":"))
                new_time = f"{max(6, h-1):02d}:{m:02d}"
                new_meal_times.append(new_time)

                cur.execute("""
                    INSERT INTO habit_adjustments (user_id, applied_on, current_value, next_suggested_value, reason, status, habit)
                    VALUES (%s, CURRENT_DATE, %s, %s, %s, 'pending', %s)
                """, (user_id, time, new_time, "Optimize meal timing", "meal_times"))

            adjustments.append({"habit": "meal_times", "suggested_change": new_meal_times})

        # 🔹 Bad Habits Reduction (Remove one at a time)
        if "bad_habits" not in existing_habits and isinstance(bad_habits, list) and bad_habits:
            reduced_bad_habits = bad_habits[:-1]  # Remove only one bad habit
            adjustments.append({"habit": "bad_habits", "suggested_change": reduced_bad_habits})
            cur.execute("""
                INSERT INTO habit_adjustments (user_id, applied_on, current_value, next_suggested_value, reason, status, habit)
                VALUES (%s, CURRENT_DATE, %s, %s, %s, 'pending', %s)
            """, (user_id, str(bad_habits), str(reduced_bad_habits), "Reduce negative habits", "bad_habits"))

        conn.commit()
        cur.close()
        conn.close()

        return {"adjustments": adjustments}

# ✅ Habit Update Endpoint (User Accepts/Rejects Habit Change)
class HabitUpdateRequest(BaseModel):
    status: str  # Accepts 'accepted' or 'rejected'

@app.post("/update_habit/{adjustment_id}")
async def update_habit(adjustment_id: int, request: HabitUpdateRequest):
    if request.status not in ["accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'accepted' or 'rejected'.")

    conn = get_db_connection()
    if conn:
        cur = conn.cursor()

        # Fetch the habit adjustment
        cur.execute("""
            SELECT user_id, habit, current_value, next_suggested_value 
            FROM habit_adjustments 
            WHERE adjustment_id = %s
        """, (adjustment_id,))
        
        adjustment = cur.fetchone()
        if not adjustment:
            return {"error": "❌ No habit adjustment found for this ID."}

        user_id, habit, previous_value, new_value = adjustment

        # **Move to history if accepted**
        if request.status == "accepted":
            cur.execute("""
                INSERT INTO habit_history (user_id, habit, previous_value, new_value, status)
                VALUES (%s, %s, %s, %s, 'accepted')
            """, (user_id, habit, previous_value, new_value))

        elif request.status == "rejected":
            cur.execute("""
                INSERT INTO habit_history (user_id, habit, previous_value, new_value, status)
                VALUES (%s, %s, %s, %s, 'rejected')
            """, (user_id, habit, previous_value, new_value))

        # **Delete from `habit_adjustments` after moving to history**
        cur.execute("DELETE FROM habit_adjustments WHERE adjustment_id = %s", (adjustment_id,))

        conn.commit()
        cur.close()
        conn.close()

        return {"message": f"✅ Habit adjustment {adjustment_id} marked as {request.status} and moved to history."}

# ✅ Habit Progress Tracking Endpoint
@app.get("/habit_progress/{user_id}")
async def habit_progress(user_id: int):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()

        # Fetch accepted adjustments
        cur.execute("""
            SELECT habit, current_value, next_suggested_value, status, applied_on 
            FROM habit_adjustments 
            WHERE user_id = %s 
            ORDER BY applied_on ASC;
        """, (user_id,))
        
        adjustments = cur.fetchall()
        cur.close()
        conn.close()

        if not adjustments:
            return {"message": "No habit progress data found."}

        # Structure the response
        progress_data = {
            "accepted": [],
            "pending": [],
            "rejected": []
        }

        for habit, current_value, next_suggested_value, status, applied_on in adjustments:
            entry = {
                "habit": habit,
                "previous_value": current_value,
                "new_value": next_suggested_value,
                "date": str(applied_on)
            }

            if status == "accepted":
                progress_data["accepted"].append(entry)
            elif status == "pending":
                progress_data["pending"].append(entry)
            else:
                progress_data["rejected"].append(entry)

        return progress_data
    
@app.get("/habit_history/{user_id}")
async def habit_history(user_id: int):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()

        # Fetch habit history
        cur.execute("""
            SELECT habit, previous_value, new_value, status, date_applied
            FROM habit_history
            WHERE user_id = %s
            ORDER BY date_applied DESC;
        """, (user_id,))
        
        history = cur.fetchall()
        cur.close()
        conn.close()

        if not history:
            return {"message": "No habit history found for this user."}

        # Structure the response
        history_data = {
            "accepted": [],
            "rejected": []
        }

        for habit, previous_value, new_value, status, date_applied in history:
            entry = {
                "habit": habit,
                "previous_value": previous_value,
                "new_value": new_value,
                "date": str(date_applied)
            }

            if status == "accepted":
                history_data["accepted"].append(entry)
            else:
                history_data["rejected"].append(entry)

        return history_data


@app.get("/daily_reminders/{user_id}")
async def daily_reminders(user_id: int):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()

        # Get reminders for today
        cur.execute("""
            SELECT habit, reminder_message, date_applied
            FROM habit_history
            WHERE user_id = %s AND status = 'accepted' AND date_applied = CURRENT_DATE
        """, (user_id,))
        
        reminders = cur.fetchall()
        cur.close()
        conn.close()

        if not reminders:
            return {"message": "No habit reminders for today."}

        # Structure the response
        reminder_data = []
        for habit, reminder_message, date_applied in reminders:
            reminder_data.append({
                "habit": habit,
                "reminder": reminder_message,
                "date": str(date_applied)
            })

        return {"daily_reminders": reminder_data}


@app.get("/chat_insights/{user_id}")
async def chat_insights(user_id: int):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()

        # Fetch habit history
        cur.execute("""
            SELECT habit, previous_value, new_value, status, date_applied
            FROM habit_history
            WHERE user_id = %s
            ORDER BY date_applied DESC;
        """, (user_id,))
        
        history = cur.fetchall()
        cur.close()
        conn.close()

        if not history:
            return {"message": "No habit history found for this user."}

        # Generate an AI-style response
        insights = []
        for habit, prev, new, status, date in history:
            if status == "accepted":
                insights.append(f"✅ You successfully changed {habit} from '{prev}' to '{new}' on {date}. Keep it up!")
            elif status == "rejected":
                insights.append(f"❌ You decided not to change {habit} from '{prev}' to '{new}' on {date}. That’s okay! Adjust at your own pace.")

        return {"insights": insights}


@app.get("/habit_projections/{user_id}")
async def habit_projections(user_id: int):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()

        # Fetch history of accepted habits
        cur.execute("""
            SELECT habit, previous_value, new_value, date_applied
            FROM habit_history
            WHERE user_id = %s AND status = 'accepted'
            ORDER BY date_applied ASC;
        """, (user_id,))
        
        history = cur.fetchall()
        cur.close()
        conn.close()

        if not history:
            return {"message": "No habit progress found for this user."}

        projections = {}
        for habit, prev, new, date in history:
            if habit not in projections:
                projections[habit] = {"start": prev, "current": new, "trend": []}

            projections[habit]["trend"].append((date, new))
            projections[habit]["current"] = new  # Update to latest value

        # AI-generated future projections
        future_insights = []
        for habit, data in projections.items():
            future_prediction = f"If you continue, your {habit} could improve from '{data['start']}' to '{data['current']}' within a few months!"
            future_insights.append(f"📈 {future_prediction}")

        return {"habit_projections": future_insights}


