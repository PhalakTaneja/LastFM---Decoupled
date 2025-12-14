import os
import requests
import threading
import customtkinter
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from dotenv import load_dotenv

# Visualization
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Spotify (PKCE)
import spotipy
from spotipy.oauth2 import SpotifyPKCE

load_dotenv()

# --- CONFIG ---
API_KEY = os.getenv('API_KEY')
SERVER_URL = "http://localhost:5000"
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI')

# Theme
customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("green")

class LastFmApp(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.title("Last.fm Client (Dynamic Export)")
        self.geometry("500x520") 
        self.resizable(False, False)
        
        self.setup_ui()

    def setup_ui(self):
        # Header
        self.label = customtkinter.CTkLabel(self, text="Last.fm Data Pipeline", font=("Arial", 18, "bold"))
        self.label.pack(pady=(20, 10))

        # Input
        self.username_entry = customtkinter.CTkEntry(self, width=280, placeholder_text="Enter Last.fm Username")
        self.username_entry.pack(pady=5)

        # 1. Fetch
        self.btn_fetch = customtkinter.CTkButton(self, text="1. Fetch & Store Data", 
                                                 command=self.start_fetch_thread, width=200)
        self.btn_fetch.pack(pady=(15, 5))

        # --- GLOBAL SETTINGS ---
        self.settings_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.settings_frame.pack(pady=10)
        
        customtkinter.CTkLabel(self.settings_frame, text="Limit:", text_color="gray").pack(side="left", padx=5)
        
        # The Global Limit Selector (Restored to 15)
        self.limit_selector = customtkinter.CTkSegmentedButton(self.settings_frame, values=["5", "10", "15"])
        self.limit_selector.set("5") # Default
        self.limit_selector.pack(side="left")

        # 2. Analytics
        self.btn_analytics = customtkinter.CTkButton(self, text="2. View Analytics Dashboard", 
                                                     fg_color="#444", hover_color="#333",
                                                     command=self.open_analytics, width=200)
        self.btn_analytics.pack(pady=5)

        # 3. Spotify
        self.btn_spotify = customtkinter.CTkButton(self, text="3. Export to Spotify", 
                                                   fg_color="#1DB954", hover_color="#1aa34a",
                                                   text_color="white", width=200,
                                                   command=self.start_spotify_export)
        self.btn_spotify.pack(pady=(15, 5))

        # Status
        self.status_label = customtkinter.CTkLabel(self, text="System Ready", text_color="gray")
        self.status_label.pack(side="bottom", pady=15)

    # --- PIPELINE ---
    def start_fetch_thread(self):
        username = self.username_entry.get().strip()
        if not username: return messagebox.showwarning("Input", "Enter a username.")
        
        self.update_status("Fetching data...", "yellow")
        threading.Thread(target=self.process_pipeline, args=(username,), daemon=True).start()

    def process_pipeline(self, username):
        try:
            url = f'http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={username}&api_key={API_KEY}&format=json&limit=100'
            resp = requests.get(url, timeout=10)
            data = resp.json()

            if 'error' in data:
                self.update_status(f"API Error: {data['message']}", "red")
                return

            tracks = data.get('recenttracks', {}).get('track', [])
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
                self.update_status("No history found.", "orange")
                return

            payload = {"username": username, "tracks": clean_tracks}
            api_resp = requests.post(f"{SERVER_URL}/api/tracks", json=payload)

            if api_resp.status_code == 200:
                self.update_status(f"Success: Synced {len(clean_tracks)} tracks!", "green")
            else:
                self.update_status(f"Server Error: {api_resp.text}", "red")

        except Exception as e:
            self.update_status(f"Pipeline Failed: {str(e)}", "red")

    # --- SPOTIFY LOGIC ---
    def start_spotify_export(self):
        username = self.username_entry.get().strip()
        if not username: return messagebox.showwarning("Input", "Enter a username first.")
        
        # Get the limit from the selector
        limit = self.limit_selector.get()
        
        threading.Thread(target=self.run_spotify_export, args=(username, limit), daemon=True).start()

    def run_spotify_export(self, username, limit):
        try:
            self.update_status("Opening Spotify Login...", "yellow")

            scope = "playlist-modify-public"
            sp = spotipy.Spotify(auth_manager=SpotifyPKCE(
                client_id=SPOTIPY_CLIENT_ID,
                redirect_uri=SPOTIPY_REDIRECT_URI,
                scope=scope
            ))

            user = sp.current_user()
            self.update_status(f"Logged in as {user['display_name']}", "green")

            # 2. Get Analysis (Dynamic Limit)
            resp = requests.get(f"{SERVER_URL}/api/analytics/{username}?limit={limit}")
            if resp.status_code != 200:
                self.update_status("Fetch failed. Run Step 1 first.", "red")
                return
            
            top_artists = resp.json().get('top_artists', [])
            
            if not top_artists:
                self.update_status("No artist data found.", "orange")
                return

            # 3. Create Playlist
            date_str = datetime.now().strftime("%Y-%m-%d")
            pl_name = f"Top {limit} Artists - {username} ({date_str})"
            playlist = sp.user_playlist_create(user['id'], pl_name, public=True)
            
            # 4. Find Tracks (With Progress Bar)
            track_uris = []
            total = len(top_artists)
            
            for index, item in enumerate(top_artists):
                artist = item['label']
                self.update_status(f"Searching {index+1}/{total}: {artist}...", "yellow")
                
                results = sp.search(q=f"artist:{artist}", type='track', limit=1)
                tracks = results['tracks']['items']
                if tracks:
                    track_uris.append(tracks[0]['uri'])

            # 5. Add to Playlist
            if track_uris:
                sp.playlist_add_items(playlist['id'], track_uris)
                self.update_status(f"Export Complete! ({len(track_uris)} songs)", "green")
                messagebox.showinfo("Spotify Success", f"Created playlist:\n{pl_name}")
            else:
                self.update_status("Could not find any songs.", "red")

        except Exception as e:
            self.update_status(f"Spotify Error: {e}", "red")
            print(f"DEBUG: {e}")

    # --- DASHBOARD LOGIC ---
    def open_analytics(self):
        username = self.username_entry.get().strip()
        if not username: return messagebox.showwarning("Input", "Enter a username.")
        
        # Get global limit
        current_limit = self.limit_selector.get()

        dash = customtkinter.CTkToplevel(self)
        dash.title(f"Dashboard: {username}")
        dash.geometry("800x600")
        dash.attributes('-topmost', True)

        # Tabs
        tabview = customtkinter.CTkTabview(dash)
        tabview.pack(fill="both", expand=True, padx=20, pady=20)
        self.tab_artist = tabview.add("Top Artists")
        self.tab_album = tabview.add("Top Albums")

        # Load with current limit
        self.refresh_charts(username, current_limit, tabview)

    def refresh_charts(self, username, limit, tabview):
        try:
            for w in self.tab_artist.winfo_children(): w.destroy()
            for w in self.tab_album.winfo_children(): w.destroy()

            resp = requests.get(f"{SERVER_URL}/api/analytics/{username}?limit={limit}")
            if resp.status_code != 200: return
            
            data = resp.json()
            self.embed_chart(self.tab_artist, data['top_artists'], f"Top {limit} Artists", "bar")
            self.embed_chart(self.tab_album, data['top_albums'], f"Top {limit} Albums", "barh")
            
        except Exception as e:
            messagebox.showerror("Error", f"Dashboard error: {e}")

    def embed_chart(self, parent, data, title, chart_type):
        def shorten(text, max_len=15):
            return text if len(text) <= max_len else text[:max_len-3] + "..."

        labels = [shorten(d['label']) for d in data]
        values = [d['value'] for d in data]

        fig, ax = plt.subplots(figsize=(5, 4), dpi=100)
        bg = '#2b2b2b'
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        color = '#1DB954'

        if chart_type == "bar":
            ax.bar(labels, values, color=color)
            ax.tick_params(axis='x', rotation=45, labelsize=9)
            plt.setp(ax.get_xticklabels(), ha="right", rotation_mode="anchor")
            ax.set_ylabel("Plays", color='white')
        else:
            ax.barh(labels, values, color=color)
            ax.invert_yaxis()
            ax.set_xlabel("Plays", color='white')

        ax.tick_params(colors='white')
        ax.set_title(title, color='white', fontweight='bold', pad=10)
        for s in ax.spines.values(): s.set_visible(False)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def update_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

if __name__ == "__main__":
    app = LastFmApp()
    app.mainloop()