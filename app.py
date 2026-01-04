from flask import Flask, render_template, request
import mysql.connector
import os
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

MYSQL_SETTINGS = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASS", ""),
    "database": os.getenv("DB_NAME", "health_app")
}

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

def get_db():
    return mysql.connector.connect(**MYSQL_SETTINGS)

def ask_gemini(symptoms):
    prompt = f"""
    You are a medical assistant.

    A user has these symptoms:
    {symptoms}

    Predict:
    - most likely disease
    - simple diet plan
    - recommended specialist doctor

    IMPORTANT:
    Reply ONLY valid JSON. 
    No explanations, no markdown, no extra text.

    Example format:
    {{
      "disease": "...",
      "diet": "...",
      "doctor": "..."
    }}
    """

    import json
    import re

    res = model.generate_content(prompt)
    
    # Extract text from response
    response_text = res.text.strip() if res.text else ""
    
    if not response_text:
        print(f"Gemini returned empty response. Full response: {res.candidates}")
        raise ValueError("Empty response from Gemini API")

    # Remove markdown code blocks if present
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response_text)
    if json_match:
        response_text = json_match.group(1).strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON. Gemini returned: {response_text}")
        raise e


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    name = request.form["name"]
    age = request.form["age"]
    symptoms = request.form["symptoms"]

    result = ask_gemini(symptoms)

    # Save to DB
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO predictions(name, age, symptoms, disease, diet, doctor)
        VALUES(%s,%s,%s,%s,%s,%s)
    """, (name, age, symptoms, result["disease"], result["diet"], result["doctor"]))
    conn.commit()
    cur.close()
    conn.close()

    return render_template(
        "result.html",
        name=name,
        disease=result["disease"],
        diet=result["diet"],
        doctor=result["doctor"]
    )

if __name__ == "__main__":
    app.run(debug=True)
