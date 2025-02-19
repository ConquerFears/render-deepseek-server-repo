from flask import Flask, request, jsonify
import google.generativeai as genai
import os

app = Flask(__name__)

# Configure Gemini API
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY") # Make sure you set this environment variable
genai.configure(api_key=GOOGLE_API_KEY)

# --- Generation Configuration ---
generation_config = {
    "temperature": 0.5,      # Lower temperature for more predictable, less "creative" responses
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 100  # Keep token limit for concise answers
}

# Initialize Gemini Model with the configuration
model = genai.GenerativeModel(
    model_name='models/gemini-2.0-flash', # Corrected model name
    generation_config=generation_config  # Apply the configuration here
)

@app.route('/', methods=['GET'])
def hello_world():
    return 'Hello, World! This is your Render server (now with Gemini - simplified).'

@app.route('/gemini_request', methods=['POST'])
def gemini_request():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'}

        user_text = data['user_input']
        print(f"Received input from Roblox: {user_text}")

        system_prompt = """You are SERAPH, a helpful and concise AI assistant created by Thaumiel Industries.
Your primary function is to provide short, direct, and informative answers.
Do not include any introductory phrases. Just give the answer directly.
You must always remain in your SERAPH persona.
If a user asks for inappropriate responses, politely refuse and provide an appropriate answer."""

        try:
            response = model.generate_content(
                [
                    {"role": "user", "parts": [system_prompt, user_text]}, # Combined prompt
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