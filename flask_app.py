from flask import Flask, request, jsonify
import requests
import traceback
import random
import xmlrpc.client

app = Flask(__name__)

# 🔥 Mémoire temporaire
trajets = {}

# 🔑 API GraphHopper
GRAPHOPPER_API_KEY = 'a917c6a2-7403-4784-85bb-bd87deaaabdb'

# 🔑 Connexion Odoo
ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USER = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'
common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})

@app.route('/')
def home():
    return "✅ API multi-charges en mémoire opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        payload = request.json
        print("🔥 Charge reçue :", payload)

        trajet_id = payload.get('trajet_id')
        point = payload.get('point')
        is_last = payload.get('is_last', False)

        if not trajet_id or not point:
            return jsonify({'error': 'trajet_id et point sont requis'}), 400

        # 📦 Stocker le point
        trajets.setdefault(trajet_id, []).append(point)
        print(f"📌 Points actuels pour {trajet_id} :", trajets[trajet_id])

        if not is_last:
            return jsonify({'status': 'Point ajouté', 'points_count': len(trajets[trajet_id])}), 200

        # 🚀 Calcul itinéraire une fois tous les points reçus
        points_data = trajets[trajet_id]
        coordinates = []
        noms_points = []
        for p in points_data:
            lat = float(p['x_studio_latitude'])
            lon = float(p['x_studio_longitude'])
            coordinates.append((lat, lon))
            noms_points.append(p.get('x_studio_nom_de_point', 'Point'))

        # 🔥 Appel GraphHopper
        url = 'https://graphhopper.com/api/1/route'
        params = {
            'vehicle': 'car',
            'locale': 'fr',
            'key': GRAPHOPPER_API_KEY,
            'points_encoded': 'false'
        }
        for lat, lon in coordinates:
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

        # 🔥 Données pour Odoo
        nom_trajet = f"Trajet {random.randint(1, 1000)}"
        result_data = {
            'x_name': nom_trajet,
            'x_studio_distance_km': round(distance_km, 2),
            'x_studio_dure': round(duration_min, 1),
            'x_studio_nom_du_trajet': " -> ".join(noms_points),
            'x_studio_coordonnes_gps': [[lon, lat] for lat, lon in coordinates]
        }

        print("✅ Données à envoyer vers Odoo :", result_data)

        record_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'x_trajets_optimises', 'create', [result_data]
        )
        print("✅ Enregistrement créé dans Odoo avec ID :", record_id)

        # 🧹 Nettoyer la mémoire
        del trajets[trajet_id]

        return jsonify({'status': 'Trajet optimisé et enregistré', 'odoo_record_id': record_id, **result_data})

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
