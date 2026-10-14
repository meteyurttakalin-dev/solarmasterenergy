from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import json
import io
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = "solarmaster_gizli_anahtar_3_ay"

LOCATIONS = {
    "Almanya": ["Berlin", "Dortmund", "Frankfurt", "Hamburg", "Köln", "Münih", "Stuttgart"],
    "Amerika Birleşik Devletleri": ["Boston", "Chicago", "Houston", "Los Angeles", "Miami", "New York",
                                    "San Francisco"],
    "Fransa": ["Bordo", "Lyon", "Marsilya", "Nice", "Paris", "Strazburg", "Toulouse"],
    "İngiltere": ["Birmingham", "Bristol", "Edinburgh", "Glasgow", "Leeds", "Liverpool", "Londra", "Manchester"],
    "İtalya": ["Floransa", "Milano", "Napoli", "Roma", "Torino", "Venedik", "Verona"],
    "Türkiye": ["Adana", "Ankara", "Antalya", "Bursa", "Bolu", "Gaziantep", "İstanbul", "İzmir", "Konya", "Trabzon"]
}
SORTED_LOCATIONS = dict(sorted(LOCATIONS.items()))

CITY_SOLAR_FACTORS = {
    "Antalya": 1.40, "İzmir": 1.35, "Adana": 1.30, "Konya": 1.25, "Ankara": 1.20,
    "İstanbul": 1.10, "Bursa": 1.10, "Bolu": 1.00, "Gaziantep": 1.25, "Trabzon": 0.95,
    "Miami": 1.40, "Los Angeles": 1.35, "Houston": 1.30, "San Francisco": 1.20,
    "New York": 1.00, "Chicago": 0.95, "Boston": 0.95,
    "Marsilya": 1.30, "Nice": 1.35, "Toulouse": 1.20, "Bordo": 1.10,
    "Lyon": 1.05, "Paris": 1.00, "Strazburg": 0.95,
    "Bristol": 0.85, "Londra": 0.85, "Liverpool": 0.80, "Birmingham": 0.80,
    "Leeds": 0.80, "Manchester": 0.80, "Glasgow": 0.75, "Edinburgh": 0.75,
    "Napoli": 1.35, "Roma": 1.30, "Floransa": 1.20, "Torino": 1.10,
    "Milano": 1.05, "Venedik": 1.05, "Verona": 1.05,
    "Münih": 1.00, "Frankfurt": 0.95, "Stuttgart": 0.95, "Köln": 0.90,
    "Berlin": 0.90, "Dortmund": 0.90, "Hamburg": 0.85
}


def init_sqlite_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calculations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            country TEXT,
            city TEXT,
            panel_type TEXT,
            monthly_bill REAL,
            investment_cost REAL,
            annual_savings REAL,
            amortization_period REAL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()


init_sqlite_db()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
            conn.commit()
            conn.close()
            flash('Kayıt başarılı! Lütfen giriş yapın.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Bu e-posta adresi zaten kayıtlı.', 'danger')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        # Hatasız SQL sorgusu (FROM users eklendi)
        cursor.execute("SELECT id, name, password FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            return redirect(url_for('dashboard'))
        else:
            flash('Geçersiz e-posta veya şifre.', 'danger')

    return render_template('login.html')


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    result = None
    countries = list(SORTED_LOCATIONS.keys())

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        country = request.form['country']
        city = request.form['city']
        panel_type = request.form['panel_type']
        monthly_bill = float(request.form['monthly_bill'])
        investment_cost = float(request.form['investment_cost'])

        panel_power_watt = float(request.form['panel_power_watt'])
        panel_count = int(request.form['panel_count'])
        roof_orientation = float(request.form['roof_orientation'])
        shading_factor = float(request.form['shading_factor'])
        system_loss = float(request.form['system_loss'])

        total_system_kwp = (panel_power_watt * panel_count) / 1000.0
        solar_factor = CITY_SOLAR_FACTORS.get(city, 1.0)
        efficiency_multiplier = 1.2 if panel_type == 'Monokristal' else 1.0

        annual_generation_kwh = total_system_kwp * 3.8 * 365 * solar_factor * efficiency_multiplier * roof_orientation * shading_factor * system_loss
        electricity_unit_price = 3.5
        initial_annual_savings = annual_generation_kwh * electricity_unit_price

        if initial_annual_savings > 0:
            amortization_period = round(investment_cost / initial_annual_savings, 1)
        else:
            amortization_period = 0

        degradation_rate = 0.005
        total_25_year_net_savings = 0
        current_year_savings = initial_annual_savings

        for _ in range(25):
            total_25_year_net_savings += current_year_savings
            current_year_savings *= (1 - degradation_rate)

        total_25_year_net_savings = round(total_25_year_net_savings - investment_cost, 2)

        annual_co2_saved_kg = round(annual_generation_kwh * 0.5, 0)
        equivalent_trees = round(annual_co2_saved_kg / 20, 0)

        score = 100
        ai_tips = []

        if amortization_period > 8:
            score -= 25
            ai_tips.append("Amorti süresi endüstri ortalamasının üstünde. Kurulum maliyetini optimize etmelisin.")
        elif amortization_period <= 4:
            ai_tips.append("Mükemmel geri dönüş hızı! Yatırım çok kısa sürede kendisini finanse ediyor.")

        if roof_orientation < 0.9:
            score -= 15
            ai_tips.append("Çatı yönü veya açısı ideal güney cepheden sapıyor. Verim kaybı yaşıyorsun.")

        if shading_factor < 0.9:
            score -= 20
            ai_tips.append("Gölgelenme faktörü verimliliği düşürüyor. Engelleyici nesneleri temizlemek mantıklı olur.")

        if panel_type == 'Monokristal':
            ai_tips.append("Monokristal panel tercihi düşük ışıklı günlerde bile optimum performans sağlıyor.")

        score = max(40, score)

        if score >= 85:
            ai_status = "success"
            ai_summary = f"Sistem Puanımız: {score}/100. Mükemmel Mühendislik Konfigürasyonu! {city} bölgesinde bu sistem kusursuz çalışacak."
        elif score >= 65:
            ai_status = "warning"
            ai_summary = f"Sistem Puanımız: {score}/100. Kabul Edilebilir Performans. Bazı küçük optimizasyonlarla verimi zirveye taşıyabilirsin."
        else:
            ai_status = "danger"
            ai_summary = f"Sistem Puanımız: {score}/100. Dikkat Gerektiren Konfigürasyon! Mühendislik parametrelerini gözden geçirmelisin."

        result = {
            'total_system_kwp': round(total_system_kwp, 2),
            'annual_generation_kwh': round(annual_generation_kwh, 0),
            'annual_savings': round(initial_annual_savings, 2),
            'total_25_year_net_savings': total_25_year_net_savings,
            'amortization_period': amortization_period,
            'country': country,
            'city': city,
            'monthly_bill': monthly_bill,
            'investment_cost': investment_cost,
            'annual_co2_saved_kg': annual_co2_saved_kg,
            'equivalent_trees': equivalent_trees,
            'ai_score': score,
            'ai_summary': ai_summary,
            'ai_tips': ai_tips,
            'ai_status': ai_status
        }

        session['last_result'] = result

        cursor.execute('''
            INSERT INTO calculations (user_id, country, city, panel_type, monthly_bill, investment_cost, annual_savings, amortization_period)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], country, city, panel_type, monthly_bill, investment_cost, initial_annual_savings,
              amortization_period))
        conn.commit()

    cursor.execute('''
        SELECT country, city, panel_type, monthly_bill, investment_cost, annual_savings, amortization_period 
        FROM calculations WHERE user_id = ? ORDER BY id DESC LIMIT 5
    ''', (session['user_id'],))
    history = cursor.fetchall()
    conn.close()

    return render_template('dashboard.html', countries=countries,
                           locations_json=json.dumps(SORTED_LOCATIONS, ensure_ascii=False), result=result,
                           history=history)


@app.route('/download_pdf')
def download_pdf():
    if 'last_result' not in session:
        return redirect(url_for('dashboard'))

    res = session['last_result']

    def tr_fix(text):
        if not text:
            return ""
        return str(text).replace('ç', 'c').replace('Ç', 'C') \
            .replace('ğ', 'g').replace('Ğ', 'G') \
            .replace('ı', 'i').replace('İ', 'I') \
            .replace('ö', 'o').replace('Ö', 'O') \
            .replace('ş', 's').replace('Ş', 'S') \
            .replace('ü', 'u').replace('Ü', 'U')

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=16)

    pdf.cell(200, 10, txt=tr_fix("Solar Master Energy - Profesyonel Fizibilite Raporu"), ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=tr_fix(f"Kullanici: {session.get('user_name', 'Misafir')} | AI Skor: {res['ai_score']}/100"),
             ln=True, align='C')
    pdf.ln(10)

    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=tr_fix(f"Konum: {res['city']}, {res['country']}"), ln=True)
    pdf.cell(200, 10, txt=tr_fix(f"Kurulu Sistem Gucu: {res['total_system_kwp']} kWp"), ln=True)
    pdf.cell(200, 10, txt=tr_fix(f"Yillik Enerji Uretimi: {res['annual_generation_kwh']} kWh"), ln=True)
    pdf.cell(200, 10, txt=tr_fix(f"Yillik Tasarruf: {res['annual_savings']} TL"), ln=True)
    pdf.cell(200, 10, txt=tr_fix(f"Amortisman Suresi: {res['amortization_period']} Yil"), ln=True)
    pdf.cell(200, 10, txt=tr_fix(f"25 Yillik Net Kazanc: {res['total_25_year_net_savings']} TL"), ln=True)
    pdf.cell(200, 10,
             txt=tr_fix(f"Yillik CO2 Tasarrufu: {res['annual_co2_saved_kg']} kg (~{res['equivalent_trees']} agac)"),
             ln=True)
    pdf.ln(10)

    pdf.set_font("Arial", 'B', 11)
    pdf.cell(200, 10, txt=tr_fix("Kidemli Muhendis AI Degerlendirmesi:"), ln=True)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 8, txt=tr_fix(res['ai_summary']))

    pdf_output = io.BytesIO(pdf.output(dest='S'))
    pdf_output.seek(0)

    return send_file(pdf_output, as_attachment=True, download_name="SolarMaster_Fizibilite_Raporu.pdf",
                     mimetype='application/pdf')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)