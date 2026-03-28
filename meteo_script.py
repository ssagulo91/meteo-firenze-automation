import requests
import pandas as pd
import os
import smtplib
import logging
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# -----------------------------
# LOGGING
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -----------------------------
# MAPPATURA WEATHER CODE
# -----------------------------
WEATHER_CODE_MAP = {
    0: "Sereno",
    1: "Prevalentemente sereno",
    2: "Parzialmente nuvoloso",
    3: "Coperto",
    45: "Nebbia",
    48: "Nebbia con brina",
    51: "Pioviggine leggera",
    53: "Pioviggine",
    55: "Pioviggine intensa",
    61: "Pioggia leggera",
    63: "Pioggia",
    65: "Pioggia intensa",
    71: "Neve leggera",
    73: "Neve",
    75: "Neve intensa",
    80: "Rovesci leggeri",
    81: "Rovesci",
    82: "Rovesci intensi",
    95: "Temporale",
    96: "Temporale con grandine",
    99: "Temporale forte con grandine"
}

# -----------------------------
# FUNZIONE: Recupero dati meteo
# -----------------------------
def get_weather_data():
    lat, lon = 43.7696, 11.2558
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relative_humidity_2m,precipitation_probability,"
        f"precipitation,wind_speed_10m,weathercode&wind_speed_unit=kn&timezone=Europe%2FRome"
    )

    try:
        logging.info("Richiesta dati meteo a Open-Meteo...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        required_fields = [
            "time", "temperature_2m", "relative_humidity_2m",
            "precipitation_probability", "precipitation",
            "wind_speed_10m", "weathercode"
        ]

        if "hourly" not in data or not all(f in data["hourly"] for f in required_fields):
            raise ValueError("Campi mancanti nella risposta dell'API.")

        df = pd.DataFrame(data["hourly"])
        df["time"] = pd.to_datetime(df["time"])
        
        # Prendo la data di oggi per mostrare le previsioni di oggi
        oggi = datetime.now()
        data_target = oggi.strftime("%Y-%m-%d")
        
        # Definisco l'inizio e la fine della finestra temporale per IL GIORNO STESSO
        start = datetime.strptime(data_target + " 07:00", "%Y-%m-%d %H:%M")
        end = datetime.strptime(data_target + " 23:00", "%Y-%m-%d %H:%M")

        mask = (df["time"] >= start) & (df["time"] <= end)
        report = df.loc[mask].copy()
        
        if report.empty:
            raise ValueError("Nessun dato disponibile per la fascia oraria selezionata.")

        report["Ora"] = report["time"].dt.strftime("%H:%M")
        report["Descrizione"] = report["weathercode"].map(WEATHER_CODE_MAP).fillna("N/D")

        report = report.rename(columns={
            "temperature_2m": "Temp (°C)",
            "relative_humidity_2m": "Umidità (%)",
            "wind_speed_10m": "Vento (Nodi)",
            "precipitation_probability": "Prob. Prec (%)",
            "precipitation": "Pioggia (mm)"
        })

        report["Temp (°C)"] = report["Temp (°C)"].round(1)
        report["Vento (Nodi)"] = report["Vento (Nodi)"].round(1)

        return report[[
            "Ora", "Descrizione", "Temp (°C)", "Umidità (%)",
            "Vento (Nodi)", "Prob. Prec (%)", "Pioggia (mm)"
        ]]

    except Exception as e:
        logging.error(f"Errore nel recupero dati meteo: {e}")
        return None

# -----------------------------
# FALLBACK
# -----------------------------
def fallback_weather_data():
    logging.warning("Uso fallback: dati meteo non disponibili.")
    data = {
        "Ora": ["07:00", "12:00", "18:00", "23:00"],
        "Descrizione": ["N/D", "N/D", "N/D", "N/D"],
        "Temp (°C)": [None, None, None, None],
        "Umidità (%)": [None, None, None, None],
        "Vento (Nodi)": [None, None, None, None],
        "Prob. Prec (%)": ["N/D", "N/D", "N/D", "N/D"],
        "Pioggia (mm)": ["N/D", "N/D", "N/D", "N/D"]
    }
    return pd.DataFrame(data)

# -----------------------------
# GRAFICO PNG
# -----------------------------
def generate_plot(df):
    filename = "grafico_meteo.png"

    try:
        plt.figure(figsize=(10, 6))
        plt.plot(df["Ora"], df["Temp (°C)"], marker="o", label="Temperatura (°C)")
        plt.plot(df["Ora"], df["Prob. Prec (%)"], marker="o", label="Prob. Precipitazioni (%)")
        plt.plot(df["Ora"], df["Vento (Nodi)"], marker="o", label="Vento (Nodi)")

        plt.title("Andamento Meteo - Firenze")
        plt.xlabel("Ora")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()

        plt.savefig(filename)
        plt.close()

        logging.info("Grafico PNG generato correttamente.")
        return filename

    except Exception as e:
        logging.error(f"Errore nella generazione del grafico: {e}")
        return None

# -----------------------------
# INVIO EMAIL
# -----------------------------
def send_email(data_table, fallback=False):
    mittente = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASSWORD")
    destinatario = os.environ.get("EMAIL_RECEIVER")

    if not all([mittente, password, destinatario]):
        logging.error("Credenziali email mancanti.")
        return
   # 27/03/26: commentato, voglio la data odierna
   # data_domani = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    data_oggi = datetime.now().strftime("%Y-%m-%d")

    msg = MIMEMultipart()
    msg["From"] = mittente
    msg["To"] = destinatario
    msg["Subject"] = f"Meteo Firenze: Report Orario domani {data_oggi}"

    html_table = data_table.to_html(index=False, justify="center", border=1)

    fallback_msg = ""
    if fallback:
        fallback_msg = "<p><b>⚠️ Nota:</b> I dati meteo non erano disponibili. È stato usato un report di emergenza.</p>"

    corpo_html = f"""
    <html>
    <body>
        <h2>Previsioni Orarie Firenze - {data_oggi}</h2>
        {fallback_msg}
        {html_table}
        <br>
        <p><i>Nota: I dati del vento sono espressi in Nodi (kn).</i></p>
    </body>
    </html>
    """

    msg.attach(MIMEText(corpo_html, "html"))

    # Allego il grafico PNG
    plot_file = generate_plot(data_table)
    if plot_file:
        with open(plot_file, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={plot_file}")
            msg.attach(part)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(mittente, password)
            server.send_message(msg)
        logging.info("Email inviata correttamente.")
    except Exception as e:
        logging.error(f"Errore nell'invio email: {e}")

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    df_meteo = get_weather_data()

    if df_meteo is not None:
        send_email(df_meteo, fallback=False)
    else:
        fallback_df = fallback_weather_data()
        send_email(fallback_df, fallback=True)
