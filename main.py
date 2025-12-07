import requests
import pandas as pd
import mysql.connector
import tkinter as tk
from tkinter import messagebox
import customtkinter
from datetime import datetime
import threading
import os
import dotenv 
from dotenv import load_dotenv

# Set the theme
customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("blue")

load_dotenv()

# --- CONFIGURATION ---
API_KEY = os.getenv('API_KEY')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DB = os.getenv('MYSQL_DB')
MYSQL_HOST = 'localhost'


if not API_KEY or not MYSQL_PASSWORD:
    print("Error: .env file not found or missing variables!")
    exit(1)
def fetch_and_store_tracks(username):
    """
    Runs in a separate thread to keep the GUI responsive.
    """
    try:
        # 1. Fetch from API
        url = f'http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}&api_key={API_KEY}&format=json&limit=100'
        response = requests.get(url, timeout=10) # Added timeout
        data = response.json()

        if 'error' in data:
            messagebox.showerror("Last.fm Error", f"Error: {data['message']}")
            return

        tracks = data.get('recenttracks', {}).get('track', [])

        if not tracks:
            messagebox.showinfo("No Tracks", "No recent tracks found or profile is private.")
            return

        # 2. Process Data
        track_data = []
        for track in tracks:
            # Skip 'currently playing' tracks which don't have a final timestamp yet
            ts = track.get('date', {}).get('uts')
            if not ts:
                continue
            
            try:
                played_at_dt = datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
                track_data.append((
                    track['name'],
                    track['artist']['#text'],
                    track['album']['#text'],
                    played_at_dt
                ))
            except (ValueError, TypeError):
                continue

        if not track_data:
            messagebox.showinfo("Info", "No valid historical tracks found (only currently playing?).")
            return

        # 3. Database Operations
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB
        )
        cursor = conn.cursor()

        # Sanitize table name slightly to prevent basic SQL errors
        safe_username = username.replace('-', '_').replace(' ', '_')
        table_name = f"tracks_{safe_username}"

        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255),
            artist VARCHAR(255),
            album VARCHAR(255),
            played_at DATETIME
        );
        """
        cursor.execute(create_table_sql)

        # Clear old data (Overwrite mode)
        cursor.execute(f"DELETE FROM `{table_name}`")
        cursor.execute(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = 1")

        # FAST Bulk Insert
        insert_query = f"""
        INSERT INTO `{table_name}` (name, artist, album, played_at)
        VALUES (%s, %s, %s, %s)
        """
        cursor.executemany(insert_query, track_data)

        conn.commit()
        cursor.close()
        conn.close()

        messagebox.showinfo("Success", f"Saved {len(track_data)} tracks to table '{table_name}'.")

    except requests.exceptions.RequestException:
        messagebox.showerror("Network Error", "Could not connect to Last.fm. Check your internet.")
    except mysql.connector.Error as err:
        messagebox.showerror("Database Error", f"MySQL Error: {err}")
    except Exception as e:
        messagebox.showerror("Error", f"Unexpected error:\n{e}")

# --- GUI ---
def run_gui():
    root = customtkinter.CTk()
    root.title("Last.fm Track Importer")
    root.geometry("400x180")
    root.resizable(False, False)

    # Title Label
    label = customtkinter.CTkLabel(root, text="Enter Last.fm Username:", font=("Arial", 14, "bold"))
    label.pack(pady=(20, 5))

    # Styled Entry Box
    username_entry = customtkinter.CTkEntry(root, width=250, placeholder_text="e.g. RJ")
    username_entry.pack(pady=5)

    def on_submit():
        username = username_entry.get().strip()
        if username:
            # Run the heavy task in a background thread so the UI doesn't freeze
            threading.Thread(target=fetch_and_store_tracks, args=(username,), daemon=True).start()
        else:
            messagebox.showwarning("Input Error", "Please enter a username.")

    # Action Button
    button = customtkinter.CTkButton(root, text="Fetch & Save Data", command=on_submit, width=200)
    button.pack(pady=20)

    root.mainloop()

if __name__ == '__main__':
    run_gui()