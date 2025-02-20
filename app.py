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

if __name__ == '__main__':
    app.run(debug=True)