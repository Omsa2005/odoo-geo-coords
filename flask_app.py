from flask import Flask, request, jsonify
import requests
import traceback
import uuid
import time
import xmlrpc.client

app = Flask(__name__)

# GraphHopper API
GRAPH_HOPPER_API_KEY = 'a917c6a2-7403-4784-85bb-bd87deaaabdb'

# Odoo credentials
ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USER = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

# Connexion Odoo
common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
print("✅ Connecté à Odoo avec UID :", uid)

# Stockage temporaire des trajets
trajectories = {}

@app.route('/')
def home():
    return "✅ API d'optimisation de trajet opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        payload = request.json
        print("🔥 Charge reçue :", payload)

        # Extraire ou générer un trajet_id
        trajet_id = payload.get('trajet_id') or str(uuid.uuid4())
        point = {
            'lat': float(payload['x_studio_latitude']),
            'lon': float(payload['x_studio_longitude']),
            'name': payload['x_studio_nom_de_point']
        }
        is_last = payload.get('is_last', False)

        # Ajouter le point au trajet
        if trajet_id not in trajectories:
            trajectories[trajet_id] = []
        trajectories[trajet_id].append(point)

        print(f"📦 Points pour trajet {trajet_id} :", trajectories[trajet_id])

        # Si c’est le dernier point, optimiser et envoyer à Odoo
        if is_last:
            all_points = trajectories.pop(trajet_id)
            coordinates = [[p['lon'], p['lat']] for p in all_points]

            print("📡 Envoi vers GraphHopper :", coordinates)
            gh_url = 'https://graphhopper.com/api/1/route'
            gh_params = {
                'key': GRAPH_HOPPER_API_KEY,
                'vehicle': 'car',
                'locale': 'fr',
                'instructions': 'false',
                'points_encoded': 'false'
            }
            gh_body = {
                'points': coordinates
            }

            gh_response = requests.post(gh_url, params=gh_params, json=gh_body)
            print("📡 GraphHopper status :", gh_response.status_code)
            print("📡 GraphHopper body :", gh_response.text)

            if gh_response.status_code != 200:
                return jsonify({'error': 'GraphHopper API error', 'details': gh_response.text}), 500

            gh_data = gh_response.json()
            route = gh_data['paths'][0]
            distance_km = route['distance'] / 1000
            duration_min = route['time'] / 60000

            # Enregistrer le trajet optimisé dans Odoo
            trajet_name = f"Trajet {trajet_id[:8]}"
            odoo_result = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'x_trajets_optimises', 'create',
                [{
                    'x_name': trajet_name,
                    'x_studio_distance_km': round(distance_km, 2),
                    'x_studio_dure': round(duration_min, 1),
                    'x_studio_nom_du_trajet': " -> ".join(p['name'] for p in all_points),
                    'x_studio_coordonnes_gps': str(coordinates)
                }]
            )

            print(f"✅ Trajet {trajet_name} créé dans Odoo avec ID {odoo_result}")

            return jsonify({
                'message': 'Trajet optimisé créé dans Odoo',
                'trajet_id': trajet_id,
                'odoo_id': odoo_result
            })

        return jsonify({'message': 'Point ajouté au trajet', 'trajet_id': trajet_id})

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
