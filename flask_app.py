from flask import Flask, request, jsonify
import requests
import traceback
import random
import xmlrpc.client
import uuid

app = Flask(__name__)

# 🔑 API OpenRouteService
ORS_API_KEY = '5b3ce3597851110001cf62480a32708b0250456c960d42e3850654b5'

# 🔑 Connexion Odoo
ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USER = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

# Connexion aux endpoints XML-RPC
common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

# Authentification
uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
if uid:
    print("✅ Connecté à Odoo avec UID :", uid)
else:
    print("❌ Échec de connexion à Odoo")

# 🌍 Dictionnaire pour stocker temporairement les points par trajet
trajectoires = {}

# 📍 Limites géographiques de la Tunisie
TUNISIA_BOUNDS = {
    'min_lat': 30.228,
    'max_lat': 37.535,
    'min_lon': 7.521,
    'max_lon': 11.600
}

def is_in_tunisia(lat, lon):
    """Vérifie si une coordonnée est en Tunisie"""
    return (TUNISIA_BOUNDS['min_lat'] <= lat <= TUNISIA_BOUNDS['max_lat'] and
            TUNISIA_BOUNDS['min_lon'] <= lon <= TUNISIA_BOUNDS['max_lon'])

def snap_with_osrm(lat, lon):
    """Snap une coordonnée sur la route la plus proche avec OSRM"""
    url = f"http://router.project-osrm.org/nearest/v1/driving/{lon},{lat}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'waypoints' in data and data['waypoints']:
                snapped_lon, snapped_lat = data['waypoints'][0]['location']
                print(f"🔄 Coordonnée snapée OSRM: {lat},{lon} -> {snapped_lat},{snapped_lon}")
                return snapped_lat, snapped_lon
    except Exception as e:
        print(f"❌ Erreur OSRM snap: {e}")
    # En cas d'erreur, retourne la coordonnée originale
    return lat, lon

def call_ors(points, profile="driving-car"):
    """Appelle l’API ORS pour un profil donné"""
    url = f'https://api.openrouteservice.org/v2/directions/{profile}'
    headers = {'Authorization': ORS_API_KEY, 'Content-Type': 'application/json'}
    body = {
        "coordinates": [[p['lon'], p['lat']] for p in points],
        "radiuses": [2000] * len(points),
        "instructions": False
    }
    response = requests.post(url, headers=headers, json=body)
    print(f"📡 ORS ({profile}) Response status :", response.status_code)
    print(f"📡 ORS ({profile}) Response body :", response.text)
    return response

@app.route('/')
def home():
    return "✅ API d'optimisation + Odoo opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        print("🔥 Données reçues de Odoo :", data)

        trajet_key = data.get('_action') or str(uuid.uuid4())

        if trajet_key not in trajectoires:
            trajectoires[trajet_key] = []

        # Extraire coordonnée
        lat = float(data['x_studio_latitude'])
        lon = float(data['x_studio_longitude'])
        name = data.get('x_studio_nom_de_point', f'Point {len(trajectoires[trajet_key]) + 1}')
        print(f"🛰️ Point reçu : {name} -> Lat: {lat}, Lon: {lon}")

        # Vérifier Tunisie
        if not is_in_tunisia(lat, lon):
            error_msg = f"❌ Le point '{name}' est hors des limites de la Tunisie"
            print(error_msg)
            return jsonify({'error': error_msg}), 400

        # Snap avec OSRM
        snapped_lat, snapped_lon = snap_with_osrm(lat, lon)

        trajectoires[trajet_key].append({'lat': snapped_lat, 'lon': snapped_lon, 'name': name})
        print(f"📦 Points pour le trajet [{trajet_key}] :", trajectoires[trajet_key])

        if len(trajectoires[trajet_key]) >= 2:
            points = trajectoires[trajet_key]

            # Essayer driving-car
            response = call_ors(points, profile="driving-car")

            # Fallback foot-walking
            if response.status_code != 200:
                print("⚠️ Échec driving-car, tentative foot-walking...")
                response = call_ors(points, profile="foot-walking")

            # Fallback cycling-regular
            if response.status_code != 200:
                print("⚠️ Échec foot-walking, tentative cycling-regular...")
                response = call_ors(points, profile="cycling-regular")

            if response.status_code != 200:
                error_msg = "ORS API error (car, foot, vélo échoués)"
                print(f"❌ {error_msg}")
                return jsonify({'error': error_msg, 'details': response.text}), 500

            result = response.json()

            if 'routes' in result and len(result['routes']) > 0:
                route = result['routes'][0]['summary']
                distance_km = route['distance'] / 1000
                duration_min = route['duration'] / 60

                nom_trajet = f"Trajet Optimisé {random.randint(1, 1000)}"
                result_data = {
                    'x_name': nom_trajet,
                    'x_studio_distance_km': round(distance_km, 2),
                    'x_studio_dure': round(duration_min, 1),
                    'x_studio_nom_du_trajet': " -> ".join(p['name'] for p in points),
                    'x_studio_coordonnes_gps': [[p['lon'], p['lat']] for p in points]
                }

                print("✅ Données à envoyer vers Odoo :", result_data)

                record_id = models.execute_kw(
                    ODOO_DB, uid, ODOO_PASSWORD,
                    'x_trajets_optimises',
                    'create',
                    [result_data]
                )
                print("✅ Enregistrement créé dans Odoo avec ID :", record_id)

                del trajectoires[trajet_key]

                return jsonify({'status': 'success', 'odoo_record_id': record_id, **result_data})

            else:
                error_msg = "Format de réponse ORS inattendu"
                print(f"❌ {error_msg}")
                return jsonify({'error': error_msg, 'details': result}), 500

        return jsonify({'status': 'pending', 'message': f"Point ajouté au trajet {trajet_key}"})

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
