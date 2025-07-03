from flask import Flask, request, jsonify
import requests
import xmlrpc.client
import traceback

app = Flask(__name__)

# ----- CONFIG ODOO -----
ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USER = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

# ----- CONFIG GRAPHOPPER -----
GRAPHOPPER_API_KEY = 'a917c6a2-7403-4784-85bb-bd87deaaabdb'
GRAPHOPPER_URL = 'https://graphhopper.com/api/1/route'

# Connexion Odoo XML-RPC
common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

if not uid:
    raise Exception("Échec authentification Odoo")

print(f"✅ Connecté à Odoo avec UID : {uid}")

# Stockage temporaire des points reçus, regroupés par trajet (_id)
trajets_points = {}

@app.route('/')
def home():
    return "✅ API d'optimisation de trajet opérationnelle !"

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        print("🔥 Charge reçue :", data)

        # Récupérer l'id du trajet
        trajet_id = str(data.get('_id'))
        if not trajet_id:
            return jsonify({'error': 'Identifiant trajet (_id) manquant'}), 400

        # Extraire les données du point
        try:
            lat = float(data['x_studio_latitude'])
            lon = float(data['x_studio_longitude'])
            name = data.get('x_studio_nom_de_point', 'Point sans nom')
        except Exception as e:
            return jsonify({'error': f'Données coordonnées invalides : {str(e)}'}), 400

        # Ajouter ce point à la liste pour ce trajet
        if trajet_id not in trajets_points:
            trajets_points[trajet_id] = []
        trajets_points[trajet_id].append({'lat': lat, 'lon': lon, 'name': name})

        print(f"📦 Points pour trajet {trajet_id} : {trajets_points[trajet_id]}")

        # Si on a moins de 2 points, on ne peut pas optimiser (route impossible)
        if len(trajets_points[trajet_id]) < 2:
            return jsonify({'message': 'En attente de plus de points pour optimiser le trajet', 'points_actuels': len(trajets_points[trajet_id])}), 200

        # Construire la liste coordonnée pour GraphHopper : [[lon, lat], ...]
        coords = [[p['lon'], p['lat']] for p in trajets_points[trajet_id]]

        # Préparer la requête vers GraphHopper
        params = {
            'point': [f"{p['lat']},{p['lon']}" for p in trajets_points[trajet_id]],  # Format lat,lon
            'type': 'json',
            'locale': 'fr',
            'vehicle': 'car',
            'points_encoded': 'false',
            'key': GRAPHOPPER_API_KEY,
            'optimize': 'true'  # Permet tentative d'optimisation
        }

        # GraphHopper API exige plusieurs points, on envoie tout en params 'point' multiples
        # Le param 'point' doit être répétée par point (ex: point=lat,lon&point=lat,lon&...)
        # Donc on construit la requête manuellement :

        # Construire URL params manuellement car 'point' se répète :
        url_params = '&'.join([f"point={p['lat']},{p['lon']}" for p in trajets_points[trajet_id]])
        url = f"{GRAPHOPPER_URL}?{url_params}&type=json&locale=fr&vehicle=car&points_encoded=false&key={GRAPHOPPER_API_KEY}&optimize=true"

        print("🌐 Appel GraphHopper URL:", url)
        response = requests.get(url)
        print("📡 GraphHopper Response status :", response.status_code)
        print("📡 GraphHopper Response body :", response.text)

        if response.status_code != 200:
            return jsonify({'error': 'Erreur GraphHopper', 'details': response.text}), 500

        res_json = response.json()

        # Extraire distance et durée du trajet optimisé
        try:
            path = res_json['paths'][0]
            distance_m = path.get('distance', 0)
            duration_ms = path.get('time', 0)
            coordinates = path['points']['coordinates']  # Liste [ [lon, lat], ...]
        except Exception as e:
            return jsonify({'error': 'Données de réponse GraphHopper invalides', 'details': str(e), 'response': res_json}), 500

        distance_km = round(distance_m / 1000, 2)
        duration_min = round(duration_ms / 60000, 1)

        # Préparer le nom du trajet (ex: Trajet 1, 2, ...)
        trajet_name = f"Trajet {trajet_id}"

        # Enregistrer ou mettre à jour dans Odoo
        # On cherche si le trajet existe déjà par un champ unique (ex: x_name = trajet_name)
        existing_ids = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'x_trajets_optimises', 'search',
            [[['x_name', '=', trajet_name]]]
        )

        vals = {
            'x_name': trajet_name,
            'x_studio_distance_km': distance_km,
            'x_studio_dure': duration_min,
            'x_studio_coordonnes_gps': str(coordinates),  # Stocké en string, adapte selon type champ
        }

        if existing_ids:
            # Mise à jour
            models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'x_trajets_optimises', 'write',
                [existing_ids, vals]
            )
            print(f"✏️ Trajet {trajet_name} mis à jour dans Odoo (ID {existing_ids})")
        else:
            # Création
            new_id = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'x_trajets_optimises', 'create',
                [vals]
            )
            print(f"✅ Trajet {trajet_name} créé dans Odoo avec ID {new_id}")

        # Nettoyer points après optimisation (optionnel)
        trajets_points[trajet_id] = []

        # Répondre à Odoo avec le résumé
        result = {
            'x_studio_distance_km': distance_km,
            'x_studio_dure': duration_min,
            'x_studio_nom_du_trajet': trajet_name,
            'x_studio_coordonnes_gps': coordinates,
        }

        print("✅ Résultat envoyé à Odoo :", result)
        return jsonify(result)

    except Exception as e:
        print("❌ Erreur serveur :", str(e))
        traceback.print_exc()
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=10000)
