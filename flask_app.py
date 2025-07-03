from flask import Flask, request, jsonify
import requests
import traceback
import random
import xmlrpc.client
import uuid
import math
import threading
import time

app = Flask(__name__)

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

trajectoires = {}
last_update = {}
lock = threading.Lock()

def is_in_tunisia(lat, lon):
    return 30.228 <= lat <= 37.535 and 7.521 <= lon <= 11.600

def get_osrm_table(points):
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in points)
    url = f"http://router.project-osrm.org/table/v1/driving/{coords}"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def tsp_nearest_neighbor(distances):
    n = len(distances)
    visited = [False] * n
    path = [0]
    visited[0] = True
    for _ in range(n - 1):
        last = path[-1]
        next_city = min(
            (i for i in range(n) if not visited[i]),
            key=lambda i: distances[last][i]
        )
        path.append(next_city)
        visited[next_city] = True
    return path

def format_duration(minutes):
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours}h{mins}min" if hours else f"{mins}min"

def generate_google_maps_link(points_ordered):
    base_url = "https://www.google.com/maps/dir/"
    waypoints = "/".join(f"{p['lat']},{p['lon']}" for p in points_ordered)
    return base_url + waypoints

def auto_finalize(trajet_key):
    time.sleep(10)  # ⏳ délai avant optimisation
    with lock:
        if trajet_key in trajectoires and time.time() - last_update[trajet_key] >= 10:
            points = trajectoires[trajet_key]
            if len(points) < 2:
                print(f"⚠️ Pas assez de points pour optimiser {trajet_key}")
                return

            print(f"🚀 Optimisation automatique pour {trajet_key} avec {len(points)} points")
            try:
                table = get_osrm_table(points)
                distances = table['durations']
                order = tsp_nearest_neighbor(distances)
                points_ordered = [points[i] for i in order]

                google_maps_url = generate_google_maps_link(points_ordered)

                coords = ";".join(f"{p['lon']},{p['lat']}" for p in points_ordered)
                route_url = f"http://router.project-osrm.org/route/v1/driving/{coords}?overview=false"
                route_data = requests.get(route_url).json()

                total_distance = route_data['routes'][0]['distance'] / 1000  # km
                total_duration = route_data['routes'][0]['duration'] / 60  # min

                total_distance_rounded = math.ceil(total_distance)

                nom_trajet = f"Trajet Optimisé {random.randint(1, 1000)}"
                result_data = {
                    'x_name': nom_trajet,
                    'x_studio_distance_km': total_distance_rounded,
                    'x_studio_dure': format_duration(total_duration),
                    'x_studio_nom_du_trajet': "Trajet optimisé avec plusieurs points",
                    'x_studio_coordonnes_gps': google_maps_url
                }

                print("✅ Données envoyées vers Odoo :", result_data)

                record_id = models.execute_kw(
                    ODOO_DB, uid, ODOO_PASSWORD,
                    'x_trajets_optimises',
                    'create',
                    [result_data]
                )
                print("✅ Enregistrement créé dans Odoo avec ID :", record_id)

            except Exception as e:
                print(f"❌ Erreur lors de l'optimisation automatique : {e}")
                traceback.print_exc()
            finally:
                # 🔄 Réinitialiser
                del trajectoires[trajet_key]
                del last_update[trajet_key]

@app.route('/')
def home():
    return "✅ API d'optimisation + Odoo opérationnelle (auto mode) !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        trajet_key = data.get('_action') or str(uuid.uuid4())

        with lock:
            if trajet_key not in trajectoires:
                trajectoires[trajet_key] = []
                threading.Thread(target=auto_finalize, args=(trajet_key,)).start()

            lat = float(data['x_studio_latitude'])
            lon = float(data['x_studio_longitude'])
            name = data.get('x_studio_nom_de_point', f'Point {len(trajectoires[trajet_key]) + 1}')

            if not is_in_tunisia(lat, lon):
                return jsonify({'error': f"Point '{name}' hors Tunisie"}), 400

            trajectoires[trajet_key].append({'lat': lat, 'lon': lon, 'name': name})
            last_update[trajet_key] = time.time()

            print(f"📦 Point ajouté pour {trajet_key} : {name} ({lat},{lon})")

        return jsonify({'status': 'pending', 'message': f"Point ajouté au trajet {trajet_key}"})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
