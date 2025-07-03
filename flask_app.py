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

# 📍 Définir les limites géographiques de la Tunisie
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

@app.route('/')
def home():
    return "✅ API d'optimisation + Odoo opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        print("🔥 Données reçues de Odoo :", data)

        # Identifiant unique du trajet
        trajet_key = data.get('_action') or str(uuid.uuid4())

        # Initialiser la liste des points si trajet inconnu
        if trajet_key not in trajectoires:
            trajectoires[trajet_key] = []

        # Extraire coordonnées et vérifier qu’elles sont en Tunisie
        lat = float(data['x_studio_latitude'])
        lon = float(data['x_studio_longitude'])
        name = data.get('x_studio_nom_de_point', f'Point {len(trajectoires[trajet_key]) + 1}')
        print(f"🛰️ Vérification point : {name} -> Lat: {lat}, Lon: {lon}")

        if not is_in_tunisia(lat, lon):
            error_msg = f"❌ Le point '{name}' est hors des limites de la Tunisie"
            print(error_msg)
            return jsonify({'error': error_msg}), 400

        trajectoires[trajet_key].append({'lat': lat, 'lon': lon, 'name': name})
        print(f"📦 Points pour le trajet [{trajet_key}] :", trajectoires[trajet_key])

        # Si nombre de points >= 2, on lance l’optimisation
        if len(trajectoires[trajet_key]) >= 2:
            points = trajectoires[trajet_key]

            # Appel OpenRouteService avec tous les points
            url = 'https://api.openrouteservice.org/v2/directions/driving-car'
            headers = {'Authorization': ORS_API_KEY, 'Content-Type': 'application/json'}
            body = {
                "coordinates": [[p['lon'], p['lat']] for p in points],
                "radiuses": [2000] * len(points),  # rayon de 2 km pour snapping
                "instructions": False,
                "bounding_box": [[TUNISIA_BOUNDS['min_lon'], TUNISIA_BOUNDS['min_lat']],
                                 [TUNISIA_BOUNDS['max_lon'], TUNISIA_BOUNDS['max_lat']]]  # limiter à la Tunisie
            }

            response = requests.post(url, headers=headers, json=body)
            print("📡 ORS Response status :", response.status_code)
            print("📡 ORS Response body :", response.text)

            if response.status_code != 200:
                return jsonify({'error': 'ORS API error', 'details': response.text}), 500

            result = response.json()
            route = result['features'][0]['properties']['summary']
            distance_km = route['distance'] / 1000
            duration_min = route['duration'] / 60

            # 🔥 Données pour Odoo
            nom_trajet = f"Trajet Optimisé {random.randint(1, 1000)}"
            result_data = {
                'x_name': nom_trajet,
                'x_studio_distance_km': round(distance_km, 2),
                'x_studio_dure': round(duration_min, 1),
                'x_studio_nom_du_trajet': " -> ".join(p['name'] for p in points),
                'x_studio_coordonnes_gps': [[p['lon'], p['lat']] for p in points]
            }

            print("✅ Données à envoyer vers Odoo :", result_data)

            # 📦 Créer enregistrement Odoo
            record_id = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'x_trajets_optimises',  # Nom du modèle technique
                'create',
                [result_data]
            )
            print("✅ Enregistrement créé dans Odoo avec ID :", record_id)

            # Nettoyer les points de ce trajet
            del trajectoires[trajet_key]

            return jsonify({'status': 'success', 'odoo_record_id': record_id, **result_data})

        # Sinon on attend d’autres points
        return jsonify({'status': 'pending', 'message': f"Point ajouté au trajet {trajet_key}"})

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
