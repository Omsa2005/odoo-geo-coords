from flask import Flask, request, jsonify
import requests
import traceback

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

        coordinates = []

        if isinstance(data, list):
            for point in data:
                lat = float(point['x_studio_latitude'])
                lon = float(point['x_studio_longitude'])
                coordinates.append(f"{lat},{lon}")
        elif isinstance(data, dict):
            lat = float(data['x_studio_latitude'])
            lon = float(data['x_studio_longitude'])
            coordinates.append(f"{lat},{lon}")
            coordinates.append(f"{lat},{lon}")  # doublon pour forcer le calcul
        else:
            return jsonify({'error': 'Format JSON invalide'}), 400

        if len(coordinates) < 2:
            return jsonify({'error': 'Minimum 2 points requis'}), 400

        # Construire URL de la requête GraphHopper
        url = f"https://graphhopper.com/api/1/route"
        params = {
            'point': coordinates,
            'vehicle': 'car',
            'locale': 'fr',
            'calc_points': 'true',
            'key': GRAPHOPPER_API_KEY,
            'points_encoded': 'false'
        }

        response = requests.get(url, params=params)
        print("📡 GraphHopper Response status :", response.status_code)
        print("📡 GraphHopper Response body :", response.text)

        if response.status_code != 200:
            return jsonify({'error': 'GraphHopper API error', 'details': response.text}), 500

        result = response.json()
        route = result['paths'][0]
        distance_km = route['distance'] / 1000
        duration_min = route['time'] / 1000 / 60

        result_data = {
            'x_studio_distance_km': round(distance_km, 2),
            'x_studio_dure': round(duration_min, 1),
            'x_studio_nom_du_trajet': " -> ".join([p.get('x_studio_nom_de_point', '') for p in data]) if isinstance(data, list) else data.get('x_studio_nom_de_point', ''),
            'x_studio_coordonnes_gps': [[float(p['x_studio_longitude']), float(p['x_studio_latitude'])] for p in data] if isinstance(data, list) else [[float(data['x_studio_longitude']), float(data['x_studio_latitude'])]]
        }

        print("✅ Résultat envoyé à Odoo :", result_data)
        return jsonify(result_data)

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
