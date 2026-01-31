from flask import Flask, render_template, request
import mysql.connector
import os
import google.generativeai as genai
from dotenv import load_dotenv
import requests
import json
import re

load_dotenv()

app = Flask(__name__)

# ---------------- MYSQL ----------------
MYSQL_SETTINGS = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
    "port": os.getenv("DB_PORT")
}

def get_db():
    return mysql.connector.connect(**MYSQL_SETTINGS)

# ---------------- GEMINI ----------------
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# ---------------- MAPS ----------------
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY")

# ---------------- GOOGLE MAP SEARCH ----------------
def get_nearby(lat, lon, place_type, keyword):

    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

    radii = [3000, 6000, 10000, 15000]   # meters

    places = []

    for radius in radii:

        params = {
            "location": f"{lat},{lon}",
            "radius": radius,
            "type": place_type,
            "keyword": keyword,
            "key": GOOGLE_MAPS_KEY
        }

        response = requests.get(url, params=params).json()

        for p in response.get("results", []):

            rating = p.get("rating", 0)
            reviews = p.get("user_ratings_total", 0)

            if rating >= 4.0 and reviews >= 150:

                entry = {
                    "name": p["name"],
                    "rating": rating,
                    "reviews": reviews,
                    "lat": p["geometry"]["location"]["lat"],
                    "lng": p["geometry"]["location"]["lng"]
                }

                # Avoid duplicates
                if entry not in places:
                    places.append(entry)

            if len(places) >= 5:
                return places

    return places


# ---------------- GEMINI FUNCTION ----------------
def ask_gemini(symptoms, age, gender, bmi):

    prompt = f"""
You are a medical assistant.

User Details:
Age: {age}
Gender: {gender}
BMI: {bmi}

Symptoms:
{symptoms}

Return ONLY JSON for disease name and doctor just return the keyword no need of a para:

{{
"disease": "",
"diet": "",
"doctor": ""
}}
"""

    response = model.generate_content(prompt)
    text = response.text.strip()

    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        text = match.group()

    return json.loads(text)

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():

    name = request.form["name"]
    age = request.form["age"]
    gender = request.form["gender"]
    height = float(request.form["height"])
    weight = float(request.form["weight"])
    symptoms = request.form["symptoms"]

    # LOCATION
    lat = float(request.form["latitude"])
    lon = float(request.form["longitude"])

    # BMI
    bmi = round(weight / ((height / 100) ** 2), 2)

    if bmi < 18.5:
        bmi_status = "Underweight"
    elif bmi < 25:
        bmi_status = "Normal"
    elif bmi < 30:
        bmi_status = "Overweight"
    else:
        bmi_status = "Obese"

    # GEMINI RESULT
    result = ask_gemini(symptoms, age, gender, bmi)

    doctor_type = result["doctor"]

    # GOOGLE MAP SEARCH USING GEMINI DOCTOR
    hospital_keyword = f"{doctor_type} hospital"
    lab_keyword = "diagnostic laboratory"

    hospitals = get_nearby(lat, lon, "hospital", hospital_keyword)
    labs = get_nearby(lat, lon, "diagnostic_laboratory", lab_keyword)

    # SAVE TO DB
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO predictions
        (name, age, gender, height, weight, bmi, symptoms, disease, diet, doctor)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        name, age, gender, height, weight,
        bmi, symptoms,
        result["disease"],
        result["diet"],
        doctor_type
    ))

    conn.commit()
    cur.close()
    conn.close()

    return render_template(
        "result.html",
        name=name,
        disease=result["disease"],
        diet=result["diet"],
        doctor=doctor_type,
        bmi=bmi,
        bmi_status=bmi_status,
        hospitals=hospitals,
        labs=labs
    )

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
