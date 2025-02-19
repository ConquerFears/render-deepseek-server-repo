from flask import Flask, request, jsonify
import google.generativeai as genai
import os

app = Flask(__name__)

# Configure Gemini API
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY") # Make sure you set this environment variable
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('models/gemini-2.0-flash') # Corrected model name here!

@app.route('/', methods=['GET'])
def hello_world():
    return 'Hello, World! This is your Render server (now with Gemini).'

@app.route('/gemini_request', methods=['POST']) # Renamed route for clarity
def gemini_request():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'} # Plain text error

        user_text = data['user_input']
        print(f"Received input from Roblox: {user_text}")

        try:
            response = model.generate_content( # Use Gemini API to generate content
                [
                    # REMOVED SYSTEM ROLE FOR TESTING
                    {"role": "user", "parts": [user_text]}, # User input as parts
                ],
                generation_config=genai.types.GenerationConfig(max_output_tokens=100) # Set max tokens
            )
            gemini_text_response = response.text.strip() # Get text response from Gemini
            print(f"Gemini Response: {gemini_text_response}")

            # *** Return PLAIN TEXT response ***
            return gemini_text_response, 200, {'Content-Type': 'text/plain'}

        except Exception as gemini_error:
            print(f"Error calling Gemini API: {gemini_error}")
            return "Error communicating with Gemini API", 500, {'Content-Type': 'text/plain'} # Plain text error

    except Exception as e:
        print(f"Error processing request: {e}")
        return "Internal server error", 500, {'Content-Type': 'text/plain'} # Plain text error

@app.route('/echo', methods=['POST'])
def echo_input():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'} # Plain text error

        user_text = data['user_input']
        print(f"Echoing back to Roblox: {user_text}") # Log what we are echoing

        # *** Return the received text directly as PLAIN TEXT ***
        return user_text, 200, {'Content-Type': 'text/plain'}

    except Exception as e:
        print(f"Error in /echo endpoint: {e}")
        return "Error processing echo request", 500, {'Content-Type': 'text/plain'} # Plain text error


if __name__ == '__main__':
    app.run(debug=True)