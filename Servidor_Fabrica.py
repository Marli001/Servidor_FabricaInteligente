import threading
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)
lock = threading.Lock()

# ==============================================================================
# ESTADO GLOBAL DE LA FÁBRICA INTELIGENTE
# ==============================================================================
estado_global = {
    "modoFabrica": "AUTOMATICO",
    "alarma": False,
    "nivelEnergia": 100,
    "puerta": {
        "estado": "CERRADA",
        "ultimoAcceso": "NINGUNO"
    },
    "prensa": {
        "estado": "ENCENDIDA",
        "ciclos": 0,
        "error": False
    },
    "generador": {
        "estado": "NORMAL",
        "consumo": 45
    },
    "clima_exterior": {
        "temperatura": 22.0,
        "condicion": "Despejado",
        "alerta_termica": False,
        "mal_tiempo": False
    }
}

# HILO SECUNDARIO: CONSULTA A LA API EXTERNA (OPEN-METEO)
def hilo_api_externa_clima():
    while True:
        try:
            lat, lon = 38.7054, -0.4743
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
            response = requests.get(url, timeout=3)

            if response.status_code == 200:
                data = response.json()
                temp_real = data["current"]["temperature_2m"]
                w_code = data["current"]["weather_code"]

                with lock:
                    estado_global["clima_exterior"]["temperatura"] = temp_real
                    if w_code >= 51:
                        estado_global["clima_exterior"]["condicion"] = "Lluvia / Tormenta"
                        estado_global["clima_exterior"]["mal_tiempo"] = True
                    else:
                        estado_global["clima_exterior"]["condicion"] = "Despejado"
                        estado_global["clima_exterior"]["mal_tiempo"] = False

                    if temp_real >= 47.0:
                        estado_global["clima_exterior"]["alerta_termica"] = True
                        estado_global["alarma"] = True
                        estado_global["prensa"]["estado"] = "MANTENIMIENTO"
                        estado_global["prensa"]["error"] = True
                    else:
                        estado_global["clima_exterior"]["alerta_termica"] = False
                        if estado_global["prensa"]["estado"] == "MANTENIMIENTO":
                            estado_global["prensa"]["estado"] = "ENCENDIDA"
                            estado_global["prensa"]["error"] = False
                            estado_global["alarma"] = False
        except Exception as e:
            with lock:
                print("[API Externa] Usando datos simulados de respaldo:", e)
                estado_global["clima_exterior"]["temperatura"] = 24.0
                estado_global["clima_exterior"]["condicion"] = "Despejado (Simulado)"
                estado_global["clima_exterior"]["alerta_termica"] = False
                estado_global["clima_exterior"]["mal_tiempo"] = False

        time.sleep(30)

threading.Thread(target=hilo_api_externa_clima, daemon=True).start()

@app.route("/estado_fabrica", methods=["GET"])
def obtener_todo_el_estado():
    with lock:
        return jsonify(estado_global)

@app.route("/estado_prensa", methods=["GET"])
def obtener_prensa():
    with lock:
        return jsonify({
            "nombre": "Prensa industrial",
            "estado": estado_global["prensa"]["estado"],
            "ciclos": estado_global["prensa"]["ciclos"],
            "error": estado_global["prensa"]["error"]
        })

@app.route("/estado_generador", methods=["GET"])
def obtener_generador():
    with lock:
        
        return jsonify({
            "estado": estado_global["generador"]["estado"],
            "consumo": estado_global["generador"]["consumo"],
            "nivelEnergia": estado_global["nivelEnergia"]
        })

@app.route("/api_web/prensa/ciclo", methods=["POST"])
def prensa_ciclo():

    with lock:

        if estado_global["prensa"]["error"]:
            return jsonify({"status":"error"})

        estado_global["prensa"]["estado"] = "TRABAJANDO"

        estado_global["prensa"]["ciclos"] += 1

        estado_global["nivelEnergia"] = max(
            0,
        estado_global["nivelEnergia"] - 5
        )

        energia = estado_global["nivelEnergia"]

        if energia > 50:
            estado_global["generador"]["estado"] = "NORMAL"

        elif energia > 25:
            estado_global["generador"]["estado"] = "BAJO_CONSUMO"

        else:
            estado_global["generador"]["estado"] = "CRITICO"

        def finalizar():

            with lock:

                if estado_global["prensa"]["estado"] == "TRABAJANDO":
                    estado_global["prensa"]["estado"] = "ENCENDIDA"

        threading.Timer(2.5, finalizar).start()

    return jsonify({"status":"ok"})

@app.route("/api/puerta/acceso", methods=["POST"])
def registrar_acceso():
    datos = request.get_json()

    with lock:
        estado_global["puerta"]["estado"] = "ABIERTA"
        estado_global["puerta"]["ultimoAcceso"] = datos.get("metodo", "DESCONOCIDO")

    def cerrar_puerta():
        with lock:
            estado_global["puerta"]["estado"] = "CERRADA"

    threading.Timer(3.0, cerrar_puerta).start()

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)