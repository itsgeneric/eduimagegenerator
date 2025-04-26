from flask import Flask, request, jsonify, render_template
import requests
import json
app = Flask(__name__)

with open("topics.json", "r") as f:
    ALLOWED_TOPICS = json.load(f)

SERP_API_KEY = "d824f700fc1d5c11f1580b9734410b46dd4dd46b2d7b2e730a2d612dbc6c7556"
SERP_ENDPOINT = "https://serpapi.com/search.json"

@app.route("/")
def index():
    return render_template("index.html", allowed_topics=ALLOWED_TOPICS)

@app.route("/get_keywords")
def get_keywords():
    grade = request.args.get("grade")
    subject = request.args.get("subject")
    keywords = ALLOWED_TOPICS.get(grade, {}).get(subject, [])
    return jsonify({"keywords": keywords})

@app.route("/get_image/")
def get_image():
    grade = request.args.get("grade", "")
    subject = request.args.get("subject", "")
    prompt = request.args.get("prompt", "").strip().lower()

    keywords = ALLOWED_TOPICS.get(grade, {}).get(subject, [])
    keywords_normalized = [k.lower() for k in keywords]

    if prompt not in keywords_normalized:
        return jsonify({"error": "❌ Sorry, not possible. Please enter a valid science keyword for the selected grade and subject."})

    search_term = f"{grade} {subject} {prompt} diagram"
    url = "https://serpapi.com/search.json"
    params = {
        "q": search_term,
        "tbm": "isch",
        "api_key": SERP_API_KEY
    }

    response = requests.get(url, params=params)
    data = response.json()

    images = data.get("images_results", [])
    if images:
        return jsonify({
            "title": images[0].get("title", "Result"),
            "image_url": images[0].get("original")
        })
    else:
        return jsonify({"error": "❌ No image found. Try a different valid keyword."})


@app.route("/get_image_custom")
def get_image_custom():
    query = request.args.get("query", "").strip().lower()
    if not query:
        return jsonify({"error": "❌ No search query provided."})

    search_term = f"{query} diagram"
    params = {
        "q": search_term,
        "tbm": "isch",
        "api_key": SERP_API_KEY
    }

    response = requests.get(SERP_ENDPOINT, params=params)
    data = response.json()

    images = data.get("images_results", [])
    if images:
        return jsonify({
            "title": images[0].get("title", "Result"),
            "image_url": images[0].get("original")
        })
    else:
        return jsonify({"error": "❌ No image found. Try another search."})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
