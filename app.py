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
            return jsonify({"error": "No 'user_input' provided in request body"}), 400

        user_text = data['user_input']
        print(f"Received input from Roblox: {user_text}")

        try:
            deepseek_response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": user_text},
                ],
                stream=False
            )
            deepseek_text_response = deepseek_response.choices[0].message.content.strip()
            print(f"DeepSeek Response: {deepseek_text_response}")

            # *** ENSURE you are using jsonify to return JSON response ***
            return jsonify({"status": "success", "deepseek_response": deepseek_text_response}), 200

        except Exception as deepseek_error:
            print(f"Error calling DeepSeek API: {deepseek_error}")
            return jsonify({"error": "Error communicating with DeepSeek API"}), 500

    except Exception as e:
        print(f"Error processing request: {e}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True)