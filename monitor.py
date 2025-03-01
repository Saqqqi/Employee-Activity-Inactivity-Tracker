from pynput import keyboard, mouse
import time
import logging
from datetime import datetime
import threading
import pymongo
import tkinter as tk
from tkinter import ttk
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# File to store employee session persistently
SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "employee_session.json")

print("Starting application...")
time.sleep(5)  # Delay to ensure MongoDB is ready
try:
    client = pymongo.MongoClient("mongo_url_here", serverSelectionTimeoutMS=2000)
    client.server_info()  # Test connection
    db = client["activity_tracker"]
    collection = db["inactivity_logs"]
    print("Connected to MongoDB successfully.")
except Exception as e:
    print(f"MongoDB connection failed: {e}. Continuing without DB logging.")
    logging.error(f"MongoDB connection failed: {e}")
    collection = None  # Fallback to avoid crashes

logging.basicConfig(filename="activity.log", level=logging.INFO, format="%(asctime)s: %(message)s")

# User session (in-memory, will be loaded from file if available)
user_session = {}
print("Initialized empty user_session dictionary")

last_activity_time = time.time()
inactivity_threshold = 10  # seconds
inactive_start_time = None  
popup_active = False 
lock = threading.Lock()

# Load session from file if it exists
def load_session():
    global user_session
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                stored_session = json.load(f)
                if "employee_id" in stored_session and "employee_name" in stored_session:
                    user_session = stored_session
                    print(f"Loaded session from file: {user_session}")
                else:
                    print("Session file exists but is invalid, starting fresh")
        except json.JSONDecodeError as e:
            print(f"Failed to decode session file: {e}, starting fresh")
        except Exception as e:
            print(f"Error loading session file: {e}, starting fresh")
    else:
        print(f"No session file found at {SESSION_FILE}, waiting for frontend login")

# Save session to file
def save_session():
    try:
        with open(SESSION_FILE, 'w') as f:
            json.dump(user_session, f)
        print(f"Saved session to file: {user_session} at {SESSION_FILE}")
    except Exception as e:
        print(f"Failed to save session to file: {e}")

def log_inactivity(start_time, end_time, duration, reason):
    if collection is None:  # Explicitly check if collection is None
        print("No MongoDB connection, skipping log.")
        return
    data = {
        "employee_id": user_session.get("employee_id"),
        "employee_name": user_session.get("employee_name"),
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": duration,
        "reason": reason if reason.strip() else "No reason provided",
        "reason_submitted_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    try:
        result = collection.insert_one(data)
        print(f"Inactivity logged with ID {result.inserted_id}: {data}")
        logging.info(f"Inactivity logged with ID {result.inserted_id}: {data}")
    except Exception as e:
        print(f"Failed to log inactivity in MongoDB: {e}")
        logging.error(f"Failed to log inactivity in MongoDB: {e}")

def show_inactivity_popup(start_time):
    global popup_active, last_activity_time
    with lock:
        if popup_active:
            print("Popup already active, skipping...")
            return  
        popup_active = True
        print("Popup activated")
    
    try:
        root = tk.Tk()
        root.withdraw()  
        
        def submit_reason():
            global popup_active, last_activity_time
            reason = reason_var.get()
            details = reason_details.get().strip()
            
            if reason in ["Meeting", "Other"] and not details:
                error_label.config(text="Please fill in the details!")
                return
            
            end_time = time.time()
            duration = int(end_time - start_time)
            start_time_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
            end_time_str = datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"Submitting reason: {reason}, details: {details}, duration: {duration}s")
            log_inactivity(start_time_str, end_time_str, duration, f"{reason}: {details}")
            
            last_activity_time = time.time()
            print(f"Reset last_activity_time to {datetime.fromtimestamp(last_activity_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
            popup_active = False
            print("Popup closed")
            root.destroy()
        
        popup = tk.Toplevel(root)
        popup.overrideredirect(True)  
        popup.geometry("400x300")
        popup.configure(bg="#f0f0f0")
        popup.resizable(False, False)
        popup.attributes("-topmost", True) 
        
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        x = (screen_width // 2) - (400 // 2)
        y = (screen_height // 2) - (300 // 2)
        popup.geometry(f"400x300+{x}+{y}")
        
        tk.Label(popup, text="Inactivity Detected!", font=("Helvetica", 14, "bold"), bg="#f0f0f0").pack(pady=10)
        tk.Label(popup, text="Select a reason:", font=("Helvetica", 10), bg="#f0f0f0").pack(pady=5)
        
        reason_var = tk.StringVar(value="Official Break")
        reason_dropdown = ttk.Combobox(popup, textvariable=reason_var, values=["Official Break", "Meeting", "Other"], state="readonly")
        reason_dropdown.pack(pady=5)
        
        details_label = tk.Label(popup, text="", font=("Helvetica", 10), bg="#f0f0f0")
        reason_details = tk.Entry(popup, width=40, font=("Helvetica", 10))
        
        error_label = tk.Label(popup, text="", font=("Helvetica", 10), fg="red", bg="#f0f0f0")
        error_label.pack(pady=5)
        
        def on_reason_change(event):
            reason = reason_var.get()
            if reason == "Meeting":
                details_label.config(text="What type of meeting?")
                details_label.pack(pady=5)
                reason_details.pack(pady=5)
                print(f"Reason changed to {reason}, showing details field")
            elif reason == "Other":
                details_label.config(text="Tell me reason for other break:")
                details_label.pack(pady=5)
                reason_details.pack(pady=5)
                print(f"Reason changed to {reason}, showing details field")
            else:
                details_label.pack_forget()
                reason_details.pack_forget()
                print(f"Reason changed to {reason}, hiding details field")
        
        reason_dropdown.bind("<<ComboboxSelected>>", on_reason_change)
        
        submit_button = ttk.Button(popup, text="Submit", command=submit_reason)
        submit_button.pack(pady=15)
        
        print("Popup displayed, entering mainloop")
        popup.mainloop()
    except Exception as e:
        print(f"Error in show_inactivity_popup: {e}")
        logging.error(f"Error in show_inactivity_popup: {e}")
        popup_active = False

def register_activity():
    global last_activity_time, inactive_start_time
    last_activity_time = time.time()
    inactive_start_time = None 
    print(f"Activity registered at {datetime.fromtimestamp(last_activity_time).strftime('%Y-%m-%d %H:%M:%S')}")

def on_press(key):
    try:
        print(f"Key pressed: {key}")
        register_activity()
    except Exception as e:
        print(f"Error in on_press: {e}")
        logging.error(f"Error in on_press: {e}")

def on_move(x, y):
    try:
        print(f"Mouse moved to ({x}, {y})")
        register_activity()
    except Exception as e:
        print(f"Error in on_move: {e}")
        logging.error(f"Error in on_move: {e}")

def on_click(x, y, button, pressed):
    try:
        if pressed:
            print(f"Mouse clicked at ({x}, {y}) with {button}")
            register_activity()
    except Exception as e:
        print(f"Error in on_click: {e}")
        logging.error(f"Error in on_click: {e}")

def check_inactivity():
    global last_activity_time, inactive_start_time
    print("Starting inactivity checker...")
    while True:
        try:
            if not user_session:
                print("No user session active, waiting...")
                time.sleep(1)
                continue  
            time_since_last_activity = time.time() - last_activity_time
            print(f"Time since last activity: {time_since_last_activity:.2f}s")
            if time_since_last_activity >= inactivity_threshold and inactive_start_time is None and not popup_active:
                inactive_start_time = time.time()
                print(f"Inactivity detected, starting popup at {datetime.fromtimestamp(inactive_start_time).strftime('%Y-%m-%d %H:%M:%S')}")
                threading.Thread(target=show_inactivity_popup, args=(inactive_start_time,), daemon=True).start()
            time.sleep(1)
        except Exception as e:
            print(f"Error in check_inactivity: {e}")
            logging.error(f"Error in check_inactivity: {e}")
            time.sleep(1)  # Prevent tight loop on error

def start_listeners():
    while True:  # Retry loop to keep listeners alive
        try:
            print("Starting keyboard and mouse listeners...")
            keyboard_listener = keyboard.Listener(on_press=on_press)
            mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click)
            
            keyboard_listener.start()
            mouse_listener.start()
            print("Listeners started")
            
            keyboard_listener.join()
            mouse_listener.join()
            print("Listeners stopped unexpectedly, restarting...")
        except Exception as e:
            print(f"Error in start_listeners: {e}")
            logging.error(f"Error in start_listeners: {e}")
            time.sleep(5)  # Wait before retrying

@app.route("/monitor-login", methods=["POST"])
def receive_employee():
    try:
        data = request.json
        employee_id = data.get("employee_id")
        employee_name = data.get("employee_name")
        
        print(f"Received login request: employee_id={employee_id}, employee_name={employee_name}")
        if not employee_id or not employee_name:
            print("Missing employee details, returning error")
            return jsonify({"error": "Missing employee details"}), 400
        
        user_session["employee_id"] = employee_id
        user_session["employee_name"] = employee_name
        save_session()  
        print(f"User session updated and saved: {user_session}")
        return jsonify({"message": "User session started"}), 200
    except Exception as e:
        print(f"Error in receive_employee: {e}")
        logging.error(f"Error in receive_employee: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/monitor-logout", methods=["POST"])
def clear_session():
    try:
        print("Received logout request")
        user_session.clear()
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
            print("Session file removed")
        print("User session cleared")
        return jsonify({"message": "User session cleared"}), 200
    except Exception as e:
        print(f"Error in clear_session: {e}")
        logging.error(f"Error in clear_session: {e}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    print("Loading session at startup...")
    load_session()
    
    print("Starting Flask app and background threads...")
    listener_thread = threading.Thread(target=start_listeners)
    inactivity_thread = threading.Thread(target=check_inactivity)
    flask_thread = threading.Thread(target=lambda: app.run(host="ip_of_server", port=5001))
    
    listener_thread.start()
    inactivity_thread.start()
    flask_thread.start()
    
    print(f"Flask API is running at http://ip_of_server:5001")
    
    try:
        # Keep main thread alive and allow graceful shutdown
        listener_thread.join()
        inactivity_thread.join()
        flask_thread.join()
    except KeyboardInterrupt:
        print("Shutting down gracefully...")
    except Exception as e:
        print(f"Error in main thread: {e}")
        logging.error(f"Error in main thread: {e}")