from flask import Flask, request, jsonify
import requests
import traceback
import random
import xmlrpc.client
import uuid
import math
import threading

app = Flask(__name__)

# 🔑 API OpenRouteService
ORS_API_KEY = '5b3ce3597851110001cf62480a32708b0250456c960d42e3850654b5'

# 🔑 Connexion Odoo
ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USER = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
if uid:
    print("✅ Connecté à Odoo avec UID :", uid)
else:
    print("❌ Échec de connexion à Odoo")

# Stockage points et timers
trajectoires = {}
timers = {}
LOCK = threading.Lock()

def finalize_trajet(trajet_key):
    with LOCK:
        points = trajectoires.get(trajet_key)
        if not points or len(points) < 2:
            print(f"⏳ Trajet {trajet_key} trop court ou inexistant, finalisation annulée.")
            if trajet_key in trajectoires:
                del trajectoires[trajet_key]
            if trajet_key in timers:
                del timers[trajet_key]
            return

    print(f"🚀 Finalisation automatique du trajet {trajet_key} avec {len(points)} points...")

    try:
        url_opt = 'https://api.openrouteservice.org/optimization'
        headers = {'Authorization': ORS_API_KEY, 'Content-Type': 'application/json'}

        jobs = [{"id": i+1, "location": [p['lon'], p['lat']]} for i, p in enumerate(points)]
        vehicle = {
            "id": 1,
            "start": [points[0]['lon'], points[0]['lat']],
            "end": [points[0]['lon'], points[0]['lat']],
            "capacity": [100],
            "time_window": [0, 86400]
        }

        body = {
            "jobs": jobs,
            "vehicles": [vehicle]
        }

        response = requests.post(url_opt, headers=headers, json=body)
        response.raise_for_status()
        result = response.json()

        # Récupération ordre optimisé des jobs
        route = result['routes'][0]
        order_ids = [stop['job'] for stop in route['stops'] if 'job' in stop]

        # Remonter les points dans l'ordre optimisé
        ordered_points = [points[i-1] for i in order_ids]

        # Calcul distance et durée totales
        distance_m = sum(leg['distance'] for leg in route['legs'])
        duration_s = sum(leg['duration'] for leg in route['legs'])

        distance_km = math.ceil(distance_m / 1000)
        hours = int(duration_s // 3600)
        minutes = int((duration_s % 3600) // 60)
        duree_formatee = f"{hours}h{minutes}min" if hours else f"{minutes}min"

        # Création lien Google Maps avec ordre optimisé
        google_maps_link = "https://www.google.com/maps/dir/" + "/".join(
            f"{p['lat']},{p['lon']}" for p in ordered_points
        )

        nom_trajet = f"Trajet Optimisé {random.randint(100, 999)}"
        result_data = {
            'x_name': nom_trajet,
            'x_studio_distance_km': distance_km,
            'x_studio_dure': duree_formatee,
            'x_studio_nom_du_trajet': " -> ".join(p['name'] for p in ordered_points),
            'x_studio_coordonnes_gps': google_maps_link
        }

        record_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'x_trajets_optimises',
            'create',
            [result_data]
        )
        print(f"✅ Trajet {trajet_key} enregistré dans Odoo avec ID : {record_id}")

    except Exception as e:
        print(f"❌ Erreur finalisation trajet {trajet_key} :", e)
        traceback.print_exc()

    finally:
        with LOCK:
            if trajet_key in trajectoires:
                del trajectoires[trajet_key]
            if trajet_key in timers:
                del timers[trajet_key]

@app.route('/')
def home():
    return "✅ API d'optimisation + Odoo opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        print("🔥 Données reçues :", data)

        trajet_key = data.get('_action') or str(uuid.uuid4())

        with LOCK:
            if trajet_key not in trajectoires:
                trajectoires[trajet_key] = []

            lat = float(data['x_studio_latitude'])
            lon = float(data['x_studio_longitude'])
            name = data.get('x_studio_nom_de_point', f'Point {len(trajectoires[trajet_key]) + 1}')

            trajectoires[trajet_key].append({'lat': lat, 'lon': lon, 'name': name})
            print(f"📦 Point ajouté trajet {trajet_key} : {name} ({lat},{lon})")

            if trajet_key in timers:
                timers[trajet_key].cancel()

            timer = threading.Timer(10.0, finalize_trajet, args=[trajet_key])
            timers[trajet_key] = timer
            timer.start()

        return jsonify({'status': 'pending', 'message': f"Point ajouté au trajet {trajet_key}. Finalisation auto dans 10s."})

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
