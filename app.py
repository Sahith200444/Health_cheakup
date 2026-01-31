from flask import Flask, render_template, request, redirect, session, url_for
import mysql.connector
import os
import google.generativeai as genai
from dotenv import load_dotenv
import requests
import json
import re
import bcrypt

load_dotenv()

app = Flask(__name__)
app.secret_key = "supersecretkey123"

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
    radii = [3000, 6000, 10000, 15000]
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

                if entry not in places:
                    places.append(entry)

            if len(places) >= 5:
                return places

    return places

# ---------------- GEMINI FUNCTION ----------------
def ask_gemini(symptoms, age, gender, bmi):
    prompt = f"""
Return ONLY JSON:

{{
"disease":"",
"diet":"",
"doctor":""
}}

Age:{age}
Gender:{gender}
BMI:{bmi}
Symptoms:{symptoms}
"""
    response = model.generate_content(prompt)
    text = response.text.strip()

    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        text = match.group()

    return json.loads(text)

# ================= AUTH ROUTES =================

@app.route("/", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form["email"]
        password=request.form["password"]

        db=get_db()
        cur=db.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s",(email,))
        user=cur.fetchone()

        if user and bcrypt.checkpw(password.encode(), user["password"].encode()):
            session["user"]=user["name"]
            session["user_email"]=user["email"]

            return redirect("/dashboard")

        return render_template("login.html",error="Invalid Credentials")

    return render_template("login.html")

@app.route("/signup",methods=["GET","POST"])
def signup():
    if request.method=="POST":
        name=request.form["name"]
        email=request.form["email"]
        password=bcrypt.hashpw(request.form["password"].encode(),bcrypt.gensalt()).decode()

        db=get_db()
        cur=db.cursor()
        cur.execute("INSERT INTO users(name,email,password) VALUES(%s,%s,%s)",
                    (name,email,password))
        db.commit()

        return redirect("/")

    return render_template("signup.html")

@app.route("/history")
def history():

    if "user_email" not in session:
        return redirect("/")

    db=get_db()
    cur=db.cursor(dictionary=True)

    cur.execute("""
        SELECT name,disease,doctor,bmi,diet,created_at
        FROM predictions
        WHERE user_email=%s
        ORDER BY id DESC
    """,(session["user_email"],))

    records=cur.fetchall()

    return render_template("history.html",records=records)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= MAIN APP =================

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("index.html",username=session["user"])

@app.route("/predict", methods=["POST"])
def predict():

    if "user" not in session:
        return redirect("/")

    name=request.form["name"]
    age=request.form["age"]
    gender=request.form["gender"]
    height=float(request.form["height"])
    weight=float(request.form["weight"])
    symptoms=request.form["symptoms"]
    lat=float(request.form["latitude"])
    lon=float(request.form["longitude"])

    bmi=round(weight/((height/100)**2),2)

    if bmi<18.5:
        bmi_status="Underweight"
    elif bmi<25:
        bmi_status="Normal"
    elif bmi<30:
        bmi_status="Overweight"
    else:
        bmi_status="Obese"

    result=ask_gemini(symptoms,age,gender,bmi)
    doctor=result["doctor"]

    hospitals=get_nearby(lat,lon,"hospital",f"{doctor} hospital")
    labs=get_nearby(lat,lon,"diagnostic_laboratory","diagnostic lab")

    db=get_db()
    cur=db.cursor()
    cur.execute("""
INSERT INTO predictions(user_email,name,age,gender,height,weight,bmi,symptoms,disease,diet,doctor)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
""",(
    session["user_email"],
    name,age,gender,height,weight,bmi,
    symptoms,
    result["disease"],
    result["diet"],
    doctor
))

    db.commit()

    return render_template("result.html",
        name=name,
        disease=result["disease"],
        diet=result["diet"],
        doctor=doctor,
        bmi=bmi,
        bmi_status=bmi_status,
        hospitals=hospitals,
        labs=labs
    )

# ---------------- RUN ----------------
if __name__=="__main__":
    app.run(debug=True)
