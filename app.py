from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/', methods=['GET'])  # Keep the hello world route for testing the base URL
def hello_world():
    return 'Hello, World! This is your Render server.'

@app.route('/deepseek_request', methods=['POST'])  # New route to receive data from Roblox
def deepseek_request():
    try:
        data = request.get_json()  # Try to get JSON data from the request
        if not data or 'user_input' not in data:
            return jsonify({"error": "No 'user_input' provided in request body"}), 400 # Bad request error

        user_text = data['user_input']
        print(f"Received input from Roblox: {user_text}") # For now, just print to server logs

        # In the future, we'll send 'user_text' to DeepSeek and send the response back
        response_to_roblox = {"status": "received", "message": "Input received successfully, DeepSeek integration will come next!"}
        return jsonify(response_to_roblox), 200 # OK status

    except Exception as e:
        print(f"Error processing request: {e}") # Log any errors on the server side
        return jsonify({"error": "Internal server error"}), 500 # Internal server error


if __name__ == '__main__':
    app.run(debug=True)