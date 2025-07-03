from flask import Flask, request, jsonify
import xmlrpc.client
import random
import math
import threading
import itertools
import traceback

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

# 🌍 Stockage temporaire des points
trajectoires = {}
timers = {}
LOCK = threading.Lock()

def haversine(lat1, lon1, lat2, lon2):
    """Distance en km entre deux points"""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def total_distance(order, points):
    """Distance totale pour un ordre donné"""
    dist = 0
    for i in range(len(order) - 1):
        p1, p2 = points[order[i]], points[order[i + 1]]
        dist += haversine(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
    return dist

def optimize_order(points):
    """Trouver ordre optimal (TSP)"""
    best_order = None
    min_dist = float('inf')
    for order in itertools.permutations(range(len(points))):
        dist = total_distance(order, points)
        if dist < min_dist:
            min_dist = dist
            best_order = order
    return [points[i] for i in best_order], math.ceil(min_dist)

def finalize_trajet(trajet_key):
    with LOCK:
        points = trajectoires.get(trajet_key)
        if not points or len(points) < 2:
            print(f"⏳ Pas assez de points pour {trajet_key}, finalisation annulée.")
            return

        print(f"🚀 Optimisation automatique du trajet {trajet_key}...")

        try:
            ordered_points, total_km = optimize_order(points)
            total_min = (total_km / 50) * 60  # Estimation durée à 50km/h
            hours = int(total_min // 60)
            minutes = int(total_min % 60)
            duree_formatee = f"{hours}h{minutes}min" if hours else f"{minutes}min"

            google_maps_link = "https://www.google.com/maps/dir/" + "/".join(
                f"{p['lat']},{p['lon']}" for p in ordered_points
            )

            nom_trajet = f"Trajet Optimisé {random.randint(100, 999)}"
            result_data = {
                'x_name': nom_trajet,
                'x_studio_distance_km': total_km,
                'x_studio_dure': duree_formatee,
                'x_studio_nom_du_trajet': " -> ".join(p['name'] for p in ordered_points),
                'x_studio_coordonnes_gps': google_maps_link
            }

            record_id = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'x_trajets_optimises', 'create', [result_data]
            )
            print(f"✅ Trajet enregistré dans Odoo avec ID : {record_id}")

            # Nettoyage
            del trajectoires[trajet_key]
            if trajet_key in timers:
                del timers[trajet_key]

        except Exception as e:
            print(f"❌ Erreur pendant la finalisation du trajet {trajet_key} :", e)
            traceback.print_exc()

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        print("🔥 Point reçu :", data)

        trajet_key = data.get('_action') or str(uuid.uuid4())

        with LOCK:
            if trajet_key not in trajectoires:
                trajectoires[trajet_key] = []

            lat = float(data['x_studio_latitude'])
            lon = float(data['x_studio_longitude'])
            name = data.get('x_studio_nom_de_point', f'Point {len(trajectoires[trajet_key]) + 1}')

            trajectoires[trajet_key].append({'lat': lat, 'lon': lon, 'name': name})
            print(f"📦 Point ajouté pour {trajet_key} : {name} ({lat},{lon})")

            # Reset timer
            if trajet_key in timers:
                timers[trajet_key].cancel()

            timer = threading.Timer(10.0, finalize_trajet, args=[trajet_key])
            timers[trajet_key] = timer
            timer.start()

        return jsonify({
            'status': 'pending',
            'message': f"Point ajouté à {trajet_key}. Optimisation dans 10s si pas d'autres points."
        })

    except Exception as e:
        print("❌ Erreur serveur :", e)
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
