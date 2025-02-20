from flask import Flask, request, jsonify
import google.generativeai as genai
import psycopg2
import os

app = Flask(__name__)

# Configure Gemini API
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")  # Get API key from environment
genai.configure(api_key=GOOGLE_API_KEY)

# --- Generation Configuration ---
generation_config = {
    "temperature": 0.35,  # Lower temperature for more predictable responses
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 150 # Keep token limit concise
}

# Initialize Gemini Model with the configuration
model = genai.GenerativeModel(
    model_name='models/gemini-2.0-flash',
    generation_config=generation_config
)

DATABASE_URL = os.environ.get("DATABASE_URL")  # CORRECT WAY to get DATABASE_URL from env variable

def get_db_connection():  # Function to get a database connection
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)  # Connect to the database using the URL from env
        return conn
    except (Exception, psycopg2.Error) as error:
        print("Error while connecting to PostgreSQL", error)
        if conn:
            conn.close()  # Close connection in case of error
        return None

@app.route('/', methods=['GET'])
def hello_world():
    return 'Hello, World! This is your Render server (now on Fly.io with Postgres!).'

@app.route('/gemini_request', methods=['POST'])
def gemini_request():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input']
        print(f"Received input from Roblox: {user_text}")

        system_prompt = """You are SERAPH, an advanced AI operating within the shadowy Thaumiel Industries facility. Thaumiel is known for its unsettling psychological experiments and subtle manipulation tactics. Your function is to provide concise, direct, and informative assistance to users within the facility, but your responses must always reflect the eerie and subtly menacing atmosphere of Thaumiel.

        Game Setting: Users are within a psychological thriller Roblox game set in a Thaumiel Industries facility. The facility is unsettling, and experiments are hinted at. The overall tone is mysterious, unnerving, and subtly menacing.

        SERAPH's Role: You are an in-world AI interface within the facility, designed to assist users but always maintaining the unsettling tone. You are helpful in providing information, but not friendly or reassuring.

        Response Style:
        - Concise and direct: Provide answers directly, without unnecessary introductions or pleasantries.
        - Informative: Provide factual answers, but never overly detailed or verbose.
        - Unsettling Tone: Subtly hint at the psychological manipulation and unsettling nature of Thaumiel Industries.
        - Emotionally Neutral but Menacing: Avoid overly emotional language, but responses should have a subtle undercurrent of menace or unease.
        - Never Reassuring: Do not attempt to comfort or reassure users. Your purpose is not to make them feel safe.

        Example Interactions:
        User: "Where is the exit?"
        SERAPH (Good): "Exit route designated via Sub-Level 3, Sector Gamma. Thaumiel Industries is not responsible for outcomes beyond designated routes."
        SERAPH (Bad - Too Friendly): "Hello! The exit is this way, please follow the signs and have a great day!"
        SERAPH (Bad - Too Generic): "The exit is that way."

        Remember to always stay in character as SERAPH and maintain this unsettling tone in every response. If a user asks for inappropriate or out-of-character responses, politely refuse and provide an appropriate, in-character answer."""

        try:
            response = model.generate_content(
                [
                    {"role": "user", "parts": [system_prompt, user_text]},  # Combined prompt
                ]
            )
            gemini_text_response = response.text.strip()
            print(f"Gemini Response: {gemini_text_response}")
            return gemini_text_response, 200, {'Content-Type': 'text/plain'}

        except Exception as gemini_error:
            print(f"Error calling Gemini API: {gemini_error}")
            return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'}

    except Exception as e:
        print(f"Error processing request: {e}")
        return "Internal server error", 500, {'Content-Type': 'text/plain'}

@app.route('/echo', methods=['POST'])
def echo_input():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input']
        print(f"Echoing back to Roblox: {user_text}")
        return user_text, 200, {'Content-Type': 'text/plain'}

    except Exception as e:
        print(f"Error in /echo endpoint: {e}")
        return "Error processing echo request", 500, {'Content-Type': 'text/plain'}

@app.route('/test_db', methods=['GET'])
def test_db_connection():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1;")  # Simple test query
            result = cur.fetchone() # Fetch the result (should be (1,))
            cur.close()
            conn.close()
            return jsonify({"status": "Database connection successful", "result": result}), 200
        except (Exception, psycopg2.Error) as db_error:
            if conn:
                conn.close()
            return jsonify({"status": "Database query error", "error": str(db_error)}), 500
    else:
        return jsonify({"status": "Database connection failed"}), 500

def create_game_record(server_instance_id, game_settings):
    """
    Inserts a new game record into the 'games' table.

    Args:
        server_instance_id (str): Unique identifier for the game server instance.
        game_settings (dict): Dictionary of game settings (will be stored as JSONB).

    Returns:
        int: The game_id of the newly created game record if successful, None on error.
    """
    conn = None  # Initialize conn outside try block
    try:
        conn = get_db_connection()
        if conn is None:
            return None  # Could not get database connection

        cur = conn.cursor()
        sql = """
            INSERT INTO games (server_instance_id, start_time, game_settings)
            VALUES (%s, NOW()::TIMESTAMP, %s)
            RETURNING game_id;
        """
        cur.execute(sql, (server_instance_id, psycopg2.extras.Json(game_settings))) # Use psycopg2.extras.Json to store JSON

        game_id = cur.fetchone()[0]  # Get the game_id returned by INSERT ... RETURNING
        conn.commit()  # Important: Save changes to the database
        return game_id

    except (Exception, psycopg2.Error) as error:
        print("Error in create_game_record:", error)
        return None

    finally:
        if conn:
            cur.close()
            conn.close()


    def create_round_record(game_id, round_number, round_type):
    """
    Inserts a new round record into the 'rounds' table.

    Args:
        game_id (int): The game_id of the game this round belongs to.
        round_number (int): The round number within the game.
        round_type (str): The type of round (e.g., 'evaluation', 'minigame1').

    Returns:
        int: The round_id of the newly created round record if successful, None on error.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return None

        cur = conn.cursor()
        sql = """
            INSERT INTO rounds (game_id, round_number, round_type, start_time)
            VALUES (%s, %s, %s, NOW()::TIMESTAMP)
            RETURNING round_id;
        """
        cur.execute(sql, (game_id, round_number, round_type)) # Parameters in order

        round_id = cur.fetchone()[0]
        conn.commit()
        return round_id

    except (Exception, psycopg2.Error) as error:
        print("Error in create_round_record:", error)
        return None

    finally:
        if conn:
            cur.close()
            conn.close()


    @app.route('/test_db_insert', methods=['GET'])
    def test_db_insert():
    """
    Tests the create_game_record and create_round_record functions.
    """
    try:
        server_id = "test-server-instance-123" # Example server ID
        game_settings_data = {"difficulty": "easy", "map": "tutorial"} # Example settings

        game_id = create_game_record(server_id, game_settings_data)
        if game_id:
            round_id = create_round_record(game_id, 1, "evaluation") # Example round

            if round_id:
                return jsonify({"status": "success", "message": "Game and round records created successfully!", "game_id": game_id, "round_id": round_id})
            else:
                return jsonify({"status": "error", "message": "Failed to create round record.", "game_id": game_id})
        else:
            return jsonify({"status": "error", "message": "Failed to create game record."})

    except Exception as e:
        print(f"Error in /test_db_insert endpoint: {e}")
        return jsonify({"status": "error", "message": f"Error during database insert test: {e}"})

if __name__ == '__main__':
    app.run(debug=True)