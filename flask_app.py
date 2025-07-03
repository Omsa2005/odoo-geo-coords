from flask import Flask, request, jsonify
import requests
import traceback
import random

app = Flask(__name__)
GRAPHOPPER_API_KEY = 'a917c6a2-7403-4784-85bb-bd87deaaabdb'

@app.route('/')
def home():
    return "✅ API d'optimisation de trajet (GraphHopper) opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        print("🔥 Données reçues de Odoo :", data)

        points = []
        noms_points = []

        if isinstance(data, list):
            if len(data) < 2:
                return jsonify({'error': 'Minimum 2 points requis pour optimiser le trajet'}), 400
            for point in data:
                lat = float(point['x_studio_latitude'])
                lon = float(point['x_studio_longitude'])
                points.append((lat, lon))
                noms_points.append(point.get('x_studio_nom_de_point', 'Point'))
        else:
            return jsonify({'error': 'Format JSON invalide'}), 400

        url = 'https://graphhopper.com/api/1/route'
        params = {
            'vehicle': 'car',
            'locale': 'fr',
            'key': GRAPHOPPER_API_KEY,
            'points_encoded': 'false'
        }
        # Ajoute chaque point comme paramètre 'point'
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

        # 🔥 Génère un nom pour x_name
        nom_trajet = f"Trajet {random.randint(1, 1000)}"

        result_data = {
            'x_name': nom_trajet,
            'x_studio_distance_km': round(distance_km, 2),
            'x_studio_dure': round(duration_min, 1),
            'x_studio_nom_du_trajet': " -> ".join(noms_points),
            'x_studio_coordonnes_gps': [[lon, lat] for lat, lon in points]
        }

        print("✅ Résultat envoyé à Odoo :", result_data)
        return jsonify(result_data)

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
