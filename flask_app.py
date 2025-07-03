from flask import Flask, request, jsonify
import xmlrpc.client
import requests

app = Flask(__name__)

# --- Config Odoo ---
ODOO_URL = 'https://your-odoo-url.com'
ODOO_DB = 'your_db'
ODOO_USER = 'agence-vo'
ODOO_PASS = 'Omarsalhi2005'

# --- Config GraphHopper ---
GH_API_KEY = 'a917c6a2-7403-4784-85bb-bd87deaaabdb'
GH_URL = 'https://graphhopper.com/api/1/route'

# Stock temporaire des points (en vrai, mieux avec base ou cache)
points_cache = []

def odoo_connect():
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    return uid, models

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    global points_cache
    data = request.json

    # Si data est une liste de points
    if isinstance(data, list):
        points_cache.extend(data)
    else:
        points_cache.append(data)

    # Tu peux définir ici une condition pour déclencher l’optimisation
    # Par exemple, minimum 2 points reçus
    if len(points_cache) < 2:
        return jsonify({'message': f'Points reçus : {len(points_cache)}. Envoyez au moins 2.'}), 200

    # Préparer coordonnées pour GraphHopper (lon, lat)
    coords = []
    for p in points_cache:
        lat = float(p['x_studio_latitude'])
        lon = float(p['x_studio_longitude'])
        coords.append(f"{lon},{lat}")

    params = {
        'point': coords,
        'vehicle': 'car',
        'locale': 'fr',
        'calc_points': 'true',
        'key': GH_API_KEY
    }

    try:
        response = requests.get(GH_URL, params=params)
        if response.status_code != 200:
            return jsonify({'error': 'Erreur API GraphHopper', 'details': response.text}), 500

        res = response.json()
        dist_m = res['paths'][0]['distance']
        time_ms = res['paths'][0]['time']

        # Convertir distance et durée
        dist_km = round(dist_m / 1000, 2)
        duree_min = round(time_ms / 60000, 1)

        # Connexion Odoo
        uid, models = odoo_connect()
        if not uid:
            return jsonify({'error': "Auth Odoo échouée"}), 401

        # Créer ou mettre à jour un enregistrement dans 'trajets optimisés'
        trajet_vals = {
            'x_name': 'Trajet optimisé',
            'x_studio_distance_km': dist_km,
            'x_studio_duree_min': duree_min,
            'x_studio_points': str(points_cache),  # ou format JSON
        }

        trajet_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            'x_trajets_optimises', 'create',
            [trajet_vals]
        )

        # Vide cache
        points_cache = []

        return jsonify({
            'message': 'Trajet optimisé créé dans Odoo',
            'distance_km': dist_km,
            'duree_min': duree_min,
            'trajet_id': trajet_id,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
