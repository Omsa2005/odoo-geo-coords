from flask import Flask, request, jsonify
import requests
import traceback
import random
import xmlrpc.client

app = Flask(__name__)

# 🔑 API GraphHopper
GRAPHOPPER_API_KEY = 'a917c6a2-7403-4784-85bb-bd87deaaabdb'

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

@app.route('/')
def home():
    return "✅ API d'optimisation + Odoo opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        print("🔥 Données reçues de Odoo :", data)

        points = []
        noms_points = []

        if isinstance(data, list):
            for point in data:
                lat = float(point['x_studio_latitude'])
                lon = float(point['x_studio_longitude'])
                points.append((lat, lon))
                noms_points.append(point.get('x_studio_nom_de_point', 'Point'))
        elif isinstance(data, dict):
            lat = float(data['x_studio_latitude'])
            lon = float(data['x_studio_longitude'])
            points.append((lat, lon))
            noms_points.append(data.get('x_studio_nom_de_point', 'Point'))
        else:
            return jsonify({'error': 'Format JSON invalide'}), 400

        # Si 2 points ou plus -> appel GraphHopper
        if len(points) >= 2:
            url = 'https://graphhopper.com/api/1/route'
            params = {
                'vehicle': 'car',
                'locale': 'fr',
                'key': GRAPHOPPER_API_KEY,
                'points_encoded': 'false'
            }
            for lat, lon in points:
                params = requests.compat.urlencode({'point': f"{lat},{lon}"}, doseq=True) + '&' + params

            response = requests.get(url, params=params)
            print("📡 GraphHopper Response status :", response.status_code)
            print("📡 GraphHopper Response body :", response.text)

            if response.status_code != 200:
                return jsonify({'error': 'GraphHopper API error', 'details': response.text}), 500

            result = response.json()
            route = result['paths'][0]
            distance_km = route['distance'] / 1000
            duration_min = route['time'] / 1000 / 60
        else:
            # Cas d'un seul point
            distance_km = 0
            duration_min = 0

        # 🔥 Données pour Odoo
        nom_trajet = f"Trajet {random.randint(1, 1000)}"
        result_data = {
            'x_name': nom_trajet,
            'x_studio_distance_km': round(distance_km, 2),
            'x_studio_dure': round(duration_min, 1),
            'x_studio_nom_du_trajet': " -> ".join(noms_points),
            'x_studio_coordonnes_gps': [[lon, lat] for lat, lon in points]
        }

        print("✅ Données à envoyer vers Odoo :", result_data)

        # 📦 Création de l’enregistrement dans Odoo
        record_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'x_trajets_optimises',  # Nom du modèle technique dans Odoo
            'create',
            [result_data]
        )
        print("✅ Enregistrement créé dans Odoo avec ID :", record_id)

        # Retourne aussi le JSON à l’appelant
        return jsonify({'status': 'success', 'odoo_record_id': record_id, **result_data})

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
