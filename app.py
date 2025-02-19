from flask import Flask, request, jsonify
from openai import OpenAI
import os

app = Flask(__name__)

client = OpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

@app.route('/', methods=['GET'])
def hello_world():
    return 'Hello, World! This is your Render server.'

@app.route('/deepseek_request', methods=['POST'])
def deepseek_request():
    try:
        data = request.get_json()
        if not data or 'user_input' not in data:
            return "No 'user_input' provided in request body", 400, {'Content-Type': 'text/plain'} # Plain text error

        user_text = data['user_input']
        print(f"Received input from Roblox: {user_text}")

        try:
            deepseek_response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a helpful, concise assistant. Please provide short and direct answers only."},
                    {"role": "user", "content": user_text},
                ],
                stream=False,
                max_tokens = 100 
            )
            deepseek_text_response = deepseek_response.choices[0].message.content.strip()
            print(f"DeepSeek Response: {deepseek_text_response}")

            # *** Return PLAIN TEXT response instead of JSON ***
            return deepseek_text_response, 200, {'Content-Type': 'text/plain'}

        except Exception as deepseek_error:
            print(f"Error calling DeepSeek API: {deepseek_error}")
            return "Error communicating with DeepSeek API", 500, {'Content-Type': 'text/plain'} # Plain text error

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