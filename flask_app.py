from flask import Flask, request, jsonify
import requests
import traceback
import random
import xmlrpc.client
import uuid
import threading
import math

app = Flask(__name__)

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

# 🌍 Trajets stockés
trajectoires = {}
timers = {}

def optimize_trajet(trajet_key):
    try:
        print(f"🚀 Optimisation automatique pour {trajet_key}")
        points = trajectoires[trajet_key]
        if len(points) < 2:
            print(f"⚠️ Pas assez de points pour optimiser {trajet_key}")
            return

        # Construire URL Google Maps Directions
        google_maps_url = "https://www.google.com/maps/dir/" + "/".join(
            f"{p['lat']},{p['lon']}" for p in points
        )

        # Appel Directions API (mode voiture)
        params = {
            'origin': f"{points[0]['lat']},{points[0]['lon']}",
            'destination': f"{points[-1]['lat']},{points[-1]['lon']}",
            'waypoints': "|".join(f"{p['lat']},{p['lon']}" for p in points[1:-1]),
            'key': 'AIzaSy...VOTRE_CLE_API'  # 🔑 remplace par ta clé API Google
        }
        response = requests.get("https://maps.googleapis.com/maps/api/directions/json", params=params)
        print("📡 Google Directions API Response:", response.status_code)
        directions = response.json()

        if directions['status'] != 'OK':
            raise Exception(f"Google Directions API Error: {directions['status']}")

        route = directions['routes'][0]['legs']
        total_distance = sum(leg['distance']['value'] for leg in route) / 1000  # km
        total_duration = sum(leg['duration']['value'] for leg in route) / 60    # min

        # Formater durée (ex: 3h45min)
        heures = int(total_duration // 60)
        minutes = int(total_duration % 60)
        duree_formatee = f"{heures}h{minutes}min" if heures else f"{minutes}min"

        # Arrondir distance au supérieur
        distance_arrondie = math.ceil(total_distance)

        # Préparer données pour Odoo
        result_data = {
            'x_name': f"Trajet Optimisé {random.randint(1, 1000)}",
            'x_studio_distance_km': distance_arrondie,
            'x_studio_dure': duree_formatee,
            'x_studio_nom_du_trajet': " -> ".join(p['name'] for p in points),
            'x_studio_coordonnes_gps': google_maps_url
        }

        print("✅ Données envoyées vers Odoo :", result_data)
        record_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'x_trajets_optimises',
            'create', [result_data]
        )
        print("✅ Enregistrement créé dans Odoo avec ID :", record_id)

        # Nettoyer
        del trajectoires[trajet_key]
        del timers[trajet_key]

    except Exception as e:
        print("❌ Erreur pendant optimisation :", str(e))
        traceback.print_exc()

@app.route('/optimize_route', methods=['POST'])
def add_point():
    try:
        data = request.json
        trajet_key = data.get('_action') or str(uuid.uuid4())
        lat = float(data['x_studio_latitude'])
        lon = float(data['x_studio_longitude'])
        name = data.get('x_studio_nom_de_point', f'Point {len(trajectoires.get(trajet_key, [])) + 1}')

        if trajet_key not in trajectoires:
            trajectoires[trajet_key] = []

        trajectoires[trajet_key].append({'lat': lat, 'lon': lon, 'name': name})
        print(f"📦 Point ajouté pour {trajet_key} : {name} ({lat},{lon})")

        # Relancer le timer (10 sec d'inactivité)
        if trajet_key in timers:
            timers[trajet_key].cancel()
        timers[trajet_key] = threading.Timer(10.0, optimize_trajet, args=[trajet_key])
        timers[trajet_key].start()

        return jsonify({'status': 'pending', 'message': f"Point ajouté pour {trajet_key}"})

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
