import os
import mysql.connector
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Config
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DB = os.getenv('MYSQL_DB')
MYSQL_HOST = 'localhost'

def get_db_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DB
    )

@app.route('/api/tracks', methods=['POST'])
def save_tracks():
    """
    Receives a payload of tracks and snapshots them into a user-specific table.
    """
    conn = None
    cursor = None
    try:
        data = request.json
        username = data.get('username')
        tracks = data.get('tracks')

        if not username or not tracks:
            return jsonify({"error": "Missing data"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Sanitize username for table creation
        safe_username = username.replace('-', '_').replace(' ', '_')
        table_name = f"tracks_{safe_username}"
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS `{table_name}` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255),
                artist VARCHAR(255),
                album VARCHAR(255),
                played_at DATETIME
            )
        """)
        
        # Snapshot strategy: Wipe old data to maintain only the recent batch
        cursor.execute(f"DELETE FROM `{table_name}`")
        cursor.execute(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = 1")

        sql = f"INSERT INTO `{table_name}` (name, artist, album, played_at) VALUES (%s, %s, %s, %s)"
        val = [(t['name'], t['artist'], t['album'], t['played_at']) for t in tracks]
        
        cursor.executemany(sql, val)
        conn.commit()
        
        return jsonify({"message": "Success", "count": len(tracks)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/analytics/<username>', methods=['GET'])
def get_analytics(username):
    """
    Returns aggregated top stats (Artists/Albums) for a specific user.
    """
    conn = None
    cursor = None
    try:
        limit = int(request.args.get('limit', 5)) 

        conn = get_db_connection()
        cursor = conn.cursor()
        
        safe_username = username.replace('-', '_').replace(' ', '_')
        table_name = f"tracks_{safe_username}"

        # Fetch Top Artists
        query_artists = f"""
            SELECT artist, COUNT(*) as count 
            FROM `{table_name}` 
            GROUP BY artist 
            ORDER BY count DESC 
            LIMIT {limit}
        """
        cursor.execute(query_artists)
        artists_data = [{"label": row[0], "value": row[1]} for row in cursor.fetchall()]

        # Fetch Top Albums
        query_albums = f"""
            SELECT album, COUNT(*) as count 
            FROM `{table_name}` 
            WHERE album != '' 
            GROUP BY album 
            ORDER BY count DESC 
            LIMIT {limit}
        """
        cursor.execute(query_albums)
        albums_data = [{"label": row[0], "value": row[1]} for row in cursor.fetchall()]
        
        return jsonify({
            "top_artists": artists_data,
            "top_albums": albums_data
        }), 200

    except Exception as e:
        return jsonify({"error": "No data found or DB error"}), 404
        
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)