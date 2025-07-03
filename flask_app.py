from flask import Flask, request, jsonify
import threading
import time
import requests
import xmlrpc.client

app = Flask(__name__)

# Clé API GraphHopper (à remplacer par ta clé)
GRAPH_HOPPER_API_KEY = 'a917c6a2-7403-4784-85bb-bd87deaaabdb'

# Odoo config
ODOO_URL = 'https://ton.odoo.instance'
ODOO_DB = 'ta_base_de_donnees'
ODOO_USERNAME = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

# Buffer global et timer
points_buffer = []
timer = None
lock = threading.Lock()

# Connexion Odoo XML-RPC
def odoo_connect():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
    if not uid:
        raise Exception("Connexion Odoo échouée")
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    return uid, models

# Fonction pour appeler GraphHopper
def call_graphhopper(coords):
    url = 'https://graphhopper.com/api/1/route'
    params = {
        'point': [f"{lat},{lon}" for lon, lat in coords],  # GraphHopper attend lat,lon
        'vehicle': 'car',
        'locale': 'fr',
        'calc_points': 'false',
        'key': GRAPH_HOPPER_API_KEY
    }
    # Le paramètre 'point' doit être répété pour chaque coordonnée dans l'URL
    # Donc on doit construire manuellement la query string:
    query_params = []
    for c in coords:
        query_params.append(('point', f"{c[1]},{c[0]}"))  # lat,lon
    query_params.extend([
        ('vehicle', 'car'),
        ('locale', 'fr'),
        ('calc_points', 'false'),
        ('key', GRAPH_HOPPER_API_KEY)
    ])
    response = requests.get(url, params=query_params)
    if response.status_code != 200:
        raise Exception(f"GraphHopper API error: {response.text}")
    return response.json()

# Traitement des points regroupés
def process_points():
    global points_buffer
    with lock:
        if not points_buffer:
            print("Aucun point à traiter.")
            return

        coords = [[p['lon'], p['lat']] for p in points_buffer]
        names = [p['name'] for p in points_buffer]
        print("🔥 Optimisation pour points:", coords)

        try:
            gh_result = call_graphhopper(coords)
            paths = gh_result.get('paths', [])
            if not paths:
                print("Aucun chemin retourné par GraphHopper")
                return

            distance_m = paths[0]['distance']
            time_ms = paths[0]['time']
            distance_km = round(distance_m / 1000, 2)
            duration_min = round(time_ms / 60000, 1)
            trajet_name = " -> ".join(names)

            # Connexion Odoo
            uid, models = odoo_connect()
            print(f"✅ Connecté à Odoo UID {uid}")

            # Créer enregistrement dans modèle x_trajets_optimises (à adapter)
            vals = {
                'x_name': trajet_name,
                'x_studio_distance_km': distance_km,
                'x_studio_dure': duration_min,
                'x_studio_points': str(coords)  # Stockage simple des points en texte
            }
            new_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD,
                                       'x_trajets_optimises', 'create', [vals])
            print(f"✅ Trajet optimisé créé dans Odoo, ID = {new_id}")

        except Exception as e:
            print(f"❌ Erreur lors du traitement : {e}")

        points_buffer = []

# Lance ou reset le timer
def start_timer():
    global timer
    if timer:
        timer.cancel()
    timer = threading.Timer(15.0, process_points)
    timer.start()

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    global points_buffer
    data = request.json
    try:
        lat = float(data.get('x_studio_latitude'))
        lon = float(data.get('x_studio_longitude'))
        name = data.get('x_studio_nom_de_point', '')
        point = {'lat': lat, 'lon': lon, 'name': name}
    except Exception:
        return jsonify({'error': 'Coordonnées invalides'}), 400

    with lock:
        points_buffer.append(point)
        print(f"🔥 Point ajouté : {point}")
        start_timer()

    return jsonify({'status': 'Point reçu, optimisation différée'}), 200

@app.route('/')
def home():
    return "✅ API d'optimisation de trajet opérationnelle !"

if __name__ == '__main__':
    app.run(debug=True)
