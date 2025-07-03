from flask import Flask, request, jsonify
import requests
import xmlrpc.client
import traceback

app = Flask(__name__)

ORS_API_KEY = '5b3ce3597851110001cf62480a32708b0250456c960d42e3850654b5'

ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USER = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

@app.route('/')
def home():
    return "✅ API d'optimisation de trajet opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        print("🔥 Données reçues de Odoo :", data)  # Debug

        coordinates = []

        if isinstance(data, list):
            for point in data:
                lat = float(point['x_studio_latitude'])
                lon = float(point['x_studio_longitude'])
                coordinates.append([lon, lat])
        elif isinstance(data, dict):
            lat = float(data['x_studio_latitude'])
            lon = float(data['x_studio_longitude'])
            coordinates.append([lon, lat])
            coordinates.append([lon, lat])  # doublon pour ORS
        else:
            return jsonify({'error': 'Format JSON invalide'}), 400

        if len(coordinates) < 2:
            return jsonify({'error': 'Minimum 2 points requis'}), 400

        url = 'https://api.openrouteservice.org/v2/directions/driving-car/geojson'
        headers = {'Authorization': ORS_API_KEY, 'Content-Type': 'application/json'}
        body = {'coordinates': coordinates}
        response = requests.post(url, json=body, headers=headers)

        if response.status_code != 200:
            return jsonify({'error': 'ORS API error', 'details': response.text}), 500

        ors_result = response.json()

        try:
            route = ors_result['features'][0]['properties']['summary']
            distance_km = route.get('distance', 0) / 1000
            duration_min = route.get('duration', 0) / 60
        except (KeyError, IndexError, TypeError) as e:
            return jsonify({'error': 'Résumé trajet manquant', 'ors_response': ors_result}), 500

        # Connexion Odoo
        common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
        if not uid:
            return jsonify({'error': 'Authentification Odoo échouée'}), 500

        models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

        vals = {
            'x_studio_distance_km': round(distance_km, 2),
            'x_studio_dure': round(duration_min, 1),
            'x_studio_nom_du_trajet': " -> ".join([p.get('x_studio_nom_de_point', '') for p in data]) if isinstance(data, list) else data.get('x_studio_nom_de_point', ''),
            'x_studio_coordonnes_gps': str(coordinates),
        }

        record_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD,
                                     'x_points_geographiques', 'create',
                                     [vals])

        result = {
            'record_id': record_id,
            'x_studio_distance_km': round(distance_km, 2),
            'x_studio_dure': round(duration_min, 1),
            'x_studio_nom_du_trajet': vals['x_studio_nom_du_trajet'],
            'x_studio_coordonnes_gps': coordinates
        }

        print("✅ Résultat envoyé à Odoo et créé dans la base :", result)
        return jsonify(result)

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
