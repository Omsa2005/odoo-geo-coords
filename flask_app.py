from flask import Flask, request, jsonify
import requests
import xmlrpc.client

app = Flask(__name__)

# Config Odoo
ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USERNAME = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

# Config GraphHopper
GRAPHOPPER_API_KEY = 'a917c6a2-7403-4784-85bb-bd87deaaabdb'

# Connexion à Odoo XML-RPC (login une seule fois, hors route)
common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

@app.route('/')
def home():
    return "✅ API d'optimisation de trajet opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json

        points = data.get('points')
        trajet_id = data.get('trajet_id')  # id du trajet Odoo à mettre à jour

        if not points or len(points) < 2:
            return jsonify({'error': 'Au moins 2 points requis'}), 400
        if not trajet_id:
            return jsonify({'error': 'trajet_id manquant'}), 400

        # Préparer la liste des coordonnées [lon, lat]
        coords = [[float(p['x_studio_longitude']), float(p['x_studio_latitude'])] for p in points]

        # Appel unique à GraphHopper
        url = 'https://graphhopper.com/api/1/route'
        params = {
            'point': [f"{lat},{lon}" for lon, lat in coords],  # attention ordre lat,lon dans l'URL API
            'vehicle': 'car',
            'locale': 'fr',
            'key': GRAPHOPPER_API_KEY,
            'points_encoded': 'false'
        }
        # GraphHopper API veut plusieurs 'point' paramètres, on doit envoyer la liste de points correctement
        # Donc on fait une requête GET avec multiples 'point' paramètres
        r = requests.get(url, params=[('point', f"{p[1]},{p[0]}") for p in coords] + [('vehicle','car'), ('locale','fr'), ('key',GRAPHOPPER_API_KEY), ('points_encoded','false')])
        if r.status_code != 200:
            return jsonify({'error': 'Erreur GraphHopper', 'details': r.text}), 500

        result = r.json()

        # Extraction distance et durée
        path = result['paths'][0]
        distance_km = path['distance'] / 1000
        duration_min = path['time'] / 60000

        # Préparation nom du trajet
        nom_trajet = " -> ".join(p.get('x_studio_nom_de_point', '') for p in points)

        # Mise à jour Odoo (trajet optimisé)
        vals = {
            'x_name': f"Trajet Optimisé : {nom_trajet}",
            'x_studio_distance_km': round(distance_km, 2),
            'x_studio_dure': round(duration_min, 1),
            'x_studio_coordonnes_gps': str(coords)
        }
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD,
                          'x_trajets_optimises', 'write', [[trajet_id], vals])

        return jsonify({'message': 'Trajet optimisé mis à jour', 'data': vals})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
