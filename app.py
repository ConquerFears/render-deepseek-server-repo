from flask import Flask, request, jsonify
from openai import OpenAI  # Import the OpenAI library
import os  # To access environment variables

app = Flask(__name__)

# Initialize OpenAI client - we'll set API key from environment variable later
client = OpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com") # Get API Key from environment variable

@app.route('/', methods=['GET'])
def hello_world():
    return 'Hello, World! This is your Render server.'

@app.route('/deepseek_request', methods=['POST'])
def deepseek_request():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return jsonify({"error": "No 'user_input' provided in request body"}), 400

        user_text = data['user_input']
        print(f"Received input from Roblox: {user_text}")

        # --- DeepSeek API Integration ---
        try:
            deepseek_response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": user_text}, # Use the user input from Roblox here
                ],
                stream=False
            )
            deepseek_text_response = deepseek_response.choices[0].message.content.strip() # Get the text response and remove leading/trailing whitespace
            print(f"DeepSeek Response: {deepseek_text_response}") # Log the DeepSeek response on the server

            response_to_roblox = {"status": "success", "deepseek_response": deepseek_text_response} # Include DeepSeek's response in our response to Roblox
            return jsonify(response_to_roblox), 200

        except Exception as deepseek_error: # Catch errors during DeepSeek API call
            print(f"Error calling DeepSeek API: {deepseek_error}")
            return jsonify({"error": "Error communicating with DeepSeek API"}), 500


    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True)