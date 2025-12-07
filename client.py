import os
import requests
import threading
import customtkinter
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from dotenv import load_dotenv

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

load_dotenv()

API_KEY = os.getenv('API_KEY')
SERVER_URL = "http://localhost:5000"

customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("green")

class LastFmApp(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.title("Last.fm Client")
        self.geometry("450x300")
        self.resizable(False, False)
        
        self.setup_ui()

    def setup_ui(self):
        self.label = customtkinter.CTkLabel(self, text="Last.fm Data Pipeline", font=("Arial", 16, "bold"))
        self.label.pack(pady=(20, 10))

        self.username_entry = customtkinter.CTkEntry(self, width=250, placeholder_text="Enter Username (e.g. RJ)")
        self.username_entry.pack(pady=5)

        self.btn_fetch = customtkinter.CTkButton(self, text="Fetch & Send to Server", command=self.start_fetch_thread)
        self.btn_fetch.pack(pady=15)

        self.btn_analytics = customtkinter.CTkButton(self, text="View Analytics Dashboard", 
                                                     fg_color="#444", hover_color="#333",
                                                     command=self.open_analytics)
        self.btn_analytics.pack(pady=5)

        self.status_label = customtkinter.CTkLabel(self, text="Ready", text_color="gray")
        self.status_label.pack(side="bottom", pady=10)

    def start_fetch_thread(self):
        username = self.username_entry.get().strip()
        if not username:
            messagebox.showwarning("Input", "Please enter a username.")
            return
        
        self.status_label.configure(text="Fetching data...", text_color="yellow")
        threading.Thread(target=self.process_pipeline, args=(username,), daemon=True).start()

    def process_pipeline(self, username):
        try:
            # 1. Fetch from Last.fm
            url = f'http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}&api_key={API_KEY}&format=json&limit=100'
            resp = requests.get(url, timeout=10)
            data = resp.json()

            if 'error' in data:
                self.update_status(f"Error: {data['message']}", "red")
                return

            tracks = data.get('recenttracks', {}).get('track', [])
            
            # 2. Clean Data
            clean_tracks = []
            for track in tracks:
                ts = track.get('date', {}).get('uts')
                if not ts: continue 
                
                clean_tracks.append({
                    "name": track['name'],
                    "artist": track['artist']['#text'],
                    "album": track['album']['#text'],
                    "played_at": datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
                })

            if not clean_tracks:
                self.update_status("No historical tracks found.", "orange")
                return

            # 3. Send to Local API
            payload = {"username": username, "tracks": clean_tracks}
            api_resp = requests.post(f"{SERVER_URL}/api/tracks", json=payload)

            if api_resp.status_code == 200:
                self.update_status(f"Success: Synced {len(clean_tracks)} tracks!", "green")
            else:
                self.update_status(f"Server Error: {api_resp.text}", "red")

        except Exception as e:
            self.update_status(f"Pipeline Failed: {str(e)}", "red")

    def update_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def open_analytics(self):
        username = self.username_entry.get().strip()
        if not username: 
            return messagebox.showwarning("Error", "Enter a username first.")

        dash = customtkinter.CTkToplevel(self)
        dash.title(f"Dashboard: {username}")
        dash.geometry("800x600")
        dash.attributes('-topmost', True)

        # Control Panel
        control_frame = customtkinter.CTkFrame(dash, fg_color="transparent")
        control_frame.pack(pady=10)

        label = customtkinter.CTkLabel(control_frame, text="Show Top:", font=("Arial", 12))
        label.pack(side="left", padx=10)

        self.limit_selector = customtkinter.CTkSegmentedButton(
            control_frame, 
            values=["5", "10", "15"],
            command=lambda value: self.refresh_charts(username, value, tabview)
        )
        self.limit_selector.set("5")
        self.limit_selector.pack(side="left")

        # Tabs
        tabview = customtkinter.CTkTabview(dash)
        tabview.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.tab_artist = tabview.add("Top Artists")
        self.tab_album = tabview.add("Top Albums")

        self.refresh_charts(username, "5", tabview)

    def refresh_charts(self, username, limit, tabview):
        try:
            for widget in self.tab_artist.winfo_children(): widget.destroy()
            for widget in self.tab_album.winfo_children(): widget.destroy()

            resp = requests.get(f"{SERVER_URL}/api/analytics/{username}?limit={limit}")
            if resp.status_code != 200: return
            
            data = resp.json()
            
            self.embed_chart(self.tab_artist, data['top_artists'], f"Top {limit} Artists", "bar")
            self.embed_chart(self.tab_album, data['top_albums'], f"Top {limit} Albums", "barh")
            
        except Exception as e:
             messagebox.showerror("Error", f"Could not load dashboard: {e}")

    def embed_chart(self, parent_widget, data, title, chart_type):
        def shorten_label(text, max_len=15):
            return text if len(text) <= max_len else text[:max_len-3] + "..."

        labels = [shorten_label(d['label']) for d in data]
        values = [d['value'] for d in data]

        fig, ax = plt.subplots(figsize=(5, 4), dpi=100)
        
        bg_color = '#2b2b2b' 
        bar_color = '#1f6aa5' 
        text_color = 'white'

        fig.patch.set_facecolor(bg_color)
        ax.set_facecolor(bg_color)

        if chart_type == "bar":
            ax.bar(labels, values, color=bar_color)
            ax.tick_params(axis='x', rotation=45, labelsize=9) 
            plt.setp(ax.get_xticklabels(), ha="right", rotation_mode="anchor")
            ax.set_ylabel("Number of Plays", color=text_color, fontsize=10)
            
        else:
            ax.barh(labels, values, color=bar_color)
            ax.invert_yaxis() 
            ax.set_xlabel("Number of Plays", color=text_color, fontsize=10)
            ax.tick_params(axis='y', labelsize=9)

        ax.tick_params(colors=text_color)
        ax.set_title(title, color=text_color, fontsize=12, fontweight='bold', pad=15)
        
        for spine in ax.spines.values():
            spine.set_visible(False)
            
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=parent_widget)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

if __name__ == "__main__":
    app = LastFmApp()
    app.mainloop()