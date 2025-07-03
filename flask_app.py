from flask import Flask, request, jsonify
import xmlrpc.client
import uuid
import math
import threading
import random
import logging
import traceback

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)

# 🔑 Connexion Odoo
ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USER = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

try:
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if uid:
        logging.info(f"✅ Connecté à Odoo avec UID : {uid}")
    else:
        raise Exception("❌ Échec de connexion à Odoo")
except Exception as e:
    logging.error("Erreur connexion Odoo", exc_info=True)
    raise e

# 📦 Trajets et timers
trajectoires = {}
timers = {}
LOCK = threading.Lock()

# 🌍 Fonction Haversine pour distance entre 2 points
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # rayon Terre en km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c  # distance en km

# 🧠 Algo Nearest Neighbor pour ordre optimisé
def optimize_order(points):
    if not points:
        return []

    unvisited = points.copy()
    path = [unvisited.pop(0)]  # commencer au premier point

    while unvisited:
        last = path[-1]
        next_point = min(unvisited, key=lambda p: haversine(last['lat'], last['lon'], p['lat'], p['lon']))
        path.append(next_point)
        unvisited.remove(next_point)

    return path

# 🚀 Finalise et envoie à Odoo
def finalize_trajet(trajet_key):
    with LOCK:
        points = trajectoires.get(trajet_key)
        if not points or len(points) < 2:
            logging.info(f"⏳ Trajet {trajet_key} annulé (pas assez de points)")
            trajectoires.pop(trajet_key, None)
            if trajet_key in timers:
                timers.pop(trajet_key).cancel()
            return

        logging.info(f"🚀 Optimisation du trajet {trajet_key} ({len(points)} points)")

        try:
            # 📌 Optimiser ordre
            optimized_points = optimize_order(points)
            logging.info(f"🔄 Ordre optimisé : {[p['name'] for p in optimized_points]}")

            # 📏 Distance totale
            total_distance = 0
            for i in range(len(optimized_points) - 1):
                p1 = optimized_points[i]
                p2 = optimized_points[i + 1]
                total_distance += haversine(p1['lat'], p1['lon'], p2['lat'], p2['lon'])

            distance_km = math.ceil(total_distance)  # arrondi au supérieur

            # ⏱️ Durée estimée (60 km/h)
            vitesse_moyenne = 60  # km/h
            duree_h = total_distance / vitesse_moyenne
            hours = int(duree_h)
            minutes = int((duree_h - hours) * 60)
            duree_formatee = f"{hours}h{minutes}min" if hours else f"{minutes}min"

            # 🌍 Lien Google Maps
            google_maps_link = "https://www.google.com/maps/dir/" + "/".join(
                f"{p['lat']},{p['lon']}" for p in optimized_points
            )

            # 📝 Données à envoyer
            nom_trajet = f"Trajet Optimisé {random.randint(100, 999)}"
            result_data = {
                'x_name': nom_trajet,
                'x_studio_distance_km': distance_km,
                'x_studio_dure': duree_formatee,
                'x_studio_nom_du_trajet': " -> ".join(p['name'] for p in optimized_points),
                'x_studio_coordonnes_gps': google_maps_link
            }
            logging.info(f"✅ Données envoyées à Odoo : {result_data}")

            # ✅ Enregistrement Odoo
            record_id = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'x_trajets_optimises', 'create', [result_data]
            )
            logging.info(f"✅ Trajet {trajet_key} enregistré dans Odoo (ID {record_id})")

        except Exception as e:
            logging.error(f"❌ Erreur finalisation trajet {trajet_key} :", exc_info=True)
        finally:
            trajectoires.pop(trajet_key, None)
            if trajet_key in timers:
                timers.pop(trajet_key).cancel()

@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        logging.info(f"🔥 Données reçues : {data}")

        trajet_key = data.get('_action') or str(uuid.uuid4())
        with LOCK:
            if trajet_key not in trajectoires:
                trajectoires[trajet_key] = []

            lat = float(data['x_studio_latitude'])
            lon = float(data['x_studio_longitude'])
            name = data.get('x_studio_nom_de_point', f'Point {len(trajectoires[trajet_key]) + 1}')

            trajectoires[trajet_key].append({'lat': lat, 'lon': lon, 'name': name})
            logging.info(f"📦 Point ajouté trajet {trajet_key} : {name} ({lat},{lon})")

            # ⏲️ Reset Timer (2 secondes)
            if trajet_key in timers:
                timers[trajet_key].cancel()
            timer = threading.Timer(2.0, finalize_trajet, args=[trajet_key])
            timers[trajet_key] = timer
            timer.start()

        return jsonify({'status': 'pending', 'message': f"Point ajouté au trajet {trajet_key}. Finalisation auto dans 2s sans nouvel ajout."})

    except Exception as e:
        logging.error("❌ Erreur serveur :", exc_info=True)
        return jsonify({'error': 'Erreur serveur Flask', 'details': str(e)}), 500

# NE PAS METTRE app.run() ici si tu utilises gunicorn !

# if __name__ == '__main__':
#     app.run(debug=True, host='0.0.0.0')
