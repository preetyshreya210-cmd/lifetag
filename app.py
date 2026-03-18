from flask import Flask, render_template, request, redirect, send_file
import sqlite3
import uuid
import qrcode
import os
from datetime import datetime, date
from io import BytesIO
from reportlab.pdfgen import canvas
from werkzeug.utils import secure_filename

app = Flask(__name__)

DATABASE = "lifetag.db"
UPLOAD_FOLDER = "static/uploads"

os.makedirs("static", exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def calculate_age(dob_str):
    if not dob_str:
        return "N/A"
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except:
        return "N/A"


def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY,
        profile_type TEXT,
        name TEXT,
        dob TEXT,
        blood TEXT,
        allergies TEXT,
        medicines TEXT,
        contact TEXT,
        secondary_contact TEXT,
        doctor_contact TEXT,
        critical_condition TEXT,
        emergency_instructions TEXT,
        notes TEXT,
        photo TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS scan_logs(
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        scan_time TEXT,
        access_type TEXT
    )
    """)

    conn.commit()
    conn.close()


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/create")
def create():
    return render_template("index.html")


@app.route("/register", methods=["POST"])
def register():
    user_id = str(uuid.uuid4())[:8]

    profile_type = request.form.get("profile_type", "Self")
    name = request.form["name"]
    dob = request.form.get("dob", "")
    blood = request.form["blood"]
    allergies = request.form.get("allergies", "")
    medicines = request.form.get("medicines", "")
    contact = request.form["contact"]
    secondary_contact = request.form.get("secondary_contact", "")
    doctor_contact = request.form.get("doctor_contact", "")
    critical_condition = request.form.get("critical_condition", "")
    emergency_instructions = request.form.get("emergency_instructions", "")
    notes = request.form.get("notes", "")

    photo_file = request.files.get("photo")
    photo_name = ""
    if photo_file and photo_file.filename:
        photo_name = f"{user_id}_{secure_filename(photo_file.filename)}"
        photo_file.save(os.path.join(UPLOAD_FOLDER, photo_name))

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user_id,
            profile_type,
            name,
            dob,
            blood,
            allergies,
            medicines,
            contact,
            secondary_contact,
            doctor_contact,
            critical_condition,
            emergency_instructions,
            notes,
            photo_name
        )
    )

    conn.commit()
    conn.close()

    profile_url = f"http://127.0.0.1:5000/profile/{user_id}"
    img = qrcode.make(profile_url)
    img.save(f"static/{user_id}.png")

    return render_template("success.html", user_id=user_id)


@app.route("/dashboard")
def dashboard():
    q = request.args.get("q", "").strip()

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    if q:
        cur.execute("""
            SELECT * FROM users
            WHERE id LIKE ? OR name LIKE ?
            ORDER BY name
        """, (f"%{q}%", f"%{q}%"))
    else:
        cur.execute("SELECT * FROM users ORDER BY name")

    raw_users = cur.fetchall()
    conn.close()

    users = []
    for u in raw_users:
        users.append({
            "id": u[0],
            "profile_type": u[1],
            "name": u[2],
            "dob": u[3],
            "age": calculate_age(u[3]),
            "blood": u[4]
        })

    return render_template("dashboard.html", users=users, q=q)


@app.route("/edit/<id>")
def edit(id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (id,))
    data = cur.fetchone()
    conn.close()

    if not data:
        return "Profile not found."

    return render_template("edit.html", data=data)


@app.route("/update/<id>", methods=["POST"])
def update(id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.execute("SELECT photo FROM users WHERE id=?", (id,))
    old_photo_row = cur.fetchone()
    old_photo = old_photo_row[0] if old_photo_row else ""

    photo_file = request.files.get("photo")
    photo_name = old_photo

    if photo_file and photo_file.filename:
        photo_name = f"{id}_{secure_filename(photo_file.filename)}"
        photo_file.save(os.path.join(UPLOAD_FOLDER, photo_name))

    cur.execute("""
    UPDATE users
    SET profile_type=?, name=?, dob=?, blood=?, allergies=?, medicines=?, contact=?,
        secondary_contact=?, doctor_contact=?, critical_condition=?, emergency_instructions=?,
        notes=?, photo=?
    WHERE id=?
    """,
    (
        request.form.get("profile_type", "Self"),
        request.form["name"],
        request.form.get("dob", ""),
        request.form["blood"],
        request.form.get("allergies", ""),
        request.form.get("medicines", ""),
        request.form["contact"],
        request.form.get("secondary_contact", ""),
        request.form.get("doctor_contact", ""),
        request.form.get("critical_condition", ""),
        request.form.get("emergency_instructions", ""),
        request.form.get("notes", ""),
        photo_name,
        id
    ))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


@app.route("/delete/<id>")
def delete(id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.execute("SELECT photo FROM users WHERE id=?", (id,))
    row = cur.fetchone()
    if row and row[0]:
        photo_path = os.path.join(UPLOAD_FOLDER, row[0])
        if os.path.exists(photo_path):
            os.remove(photo_path)

    cur.execute("DELETE FROM users WHERE id=?", (id,))
    cur.execute("DELETE FROM scan_logs WHERE user_id=?", (id,))
    conn.commit()
    conn.close()

    qr_path = os.path.join("static", f"{id}.png")
    if os.path.exists(qr_path):
        os.remove(qr_path)

    return redirect("/dashboard")


@app.route("/profile/<id>")
def profile(id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (id,))
    data = cur.fetchone()

    if not data:
        conn.close()
        return "Profile not found."

    scan_time = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    cur.execute(
        "INSERT INTO scan_logs (user_id, scan_time, access_type) VALUES (?, ?, ?)",
        (id, scan_time, "Public Emergency View")
    )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM scan_logs WHERE user_id=?", (id,))
    scan_count = cur.fetchone()[0]

    cur.execute("""
        SELECT scan_time FROM scan_logs
        WHERE user_id=?
        ORDER BY log_id DESC
        LIMIT 1
    """, (id,))
    last_scan = cur.fetchone()[0]

    conn.close()

    return render_template(
        "profile.html",
        data=data,
        age=calculate_age(data[3]),
        scan_count=scan_count,
        last_scan=last_scan
    )


@app.route("/medical/<id>")
def medical(id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (id,))
    data = cur.fetchone()

    if not data:
        conn.close()
        return "Profile not found."

    scan_time = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    cur.execute(
        "INSERT INTO scan_logs (user_id, scan_time, access_type) VALUES (?, ?, ?)",
        (id, scan_time, "Medical Responder View")
    )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM scan_logs WHERE user_id=?", (id,))
    scan_count = cur.fetchone()[0]

    cur.execute("""
        SELECT scan_time, access_type FROM scan_logs
        WHERE user_id=?
        ORDER BY log_id DESC
        LIMIT 5
    """, (id,))
    recent_logs = cur.fetchall()

    conn.close()

    return render_template(
        "medical.html",
        data=data,
        age=calculate_age(data[3]),
        scan_count=scan_count,
        recent_logs=recent_logs
    )


@app.route("/logs/<id>")
def logs(id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (id,))
    user = cur.fetchone()

    if not user:
        conn.close()
        return "Profile not found."

    cur.execute("""
        SELECT scan_time, access_type FROM scan_logs
        WHERE user_id=?
        ORDER BY log_id DESC
    """, (id,))
    logs = cur.fetchall()

    conn.close()
    return render_template("logs.html", user=user, logs=logs)


@app.route("/card/<id>")
def card(id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (id,))
    data = cur.fetchone()
    conn.close()

    if not data:
        return "Profile not found."

    return render_template("card.html", data=data, age=calculate_age(data[3]))


@app.route("/download-pdf/<id>")
def download_pdf(id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (id,))
    data = cur.fetchone()
    conn.close()

    if not data:
        return "Profile not found."

    buffer = BytesIO()
    p = canvas.Canvas(buffer)

    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, 800, "LifeTag Emergency Health Card")

    p.setFont("Helvetica", 12)
    p.drawString(50, 760, f"LifeTag ID: {data[0]}")
    p.drawString(50, 740, f"Name: {data[2]}")
    p.drawString(50, 720, f"Age: {calculate_age(data[3])}")
    p.drawString(50, 700, f"Blood Group: {data[4]}")
    p.drawString(50, 680, f"Primary Contact: {data[7]}")
    p.drawString(50, 660, f"Critical Condition: {data[10] if data[10] else 'Not specified'}")

    qr_path = os.path.join("static", f"{id}.png")
    if os.path.exists(qr_path):
        p.drawImage(qr_path, 50, 500, width=150, height=150)

    p.drawString(50, 470, "Scan QR for emergency profile")
    p.save()

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"LifeTag_{id}.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
