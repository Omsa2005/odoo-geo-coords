from flask import Flask, request, jsonify
import xmlrpc.client
import uuid
import math
import threading
import random
import logging

app = Flask(__name__)

# 📋 Configuration Odoo
ODOO_URL = 'https://agence-vo.odoo.com'
ODOO_DB = 'agence-vo'
ODOO_USER = 'salhiomar147@gmail.com'
ODOO_PASSWORD = 'Omarsalhi2005'

# 📢 Logger
logging.basicConfig(level=logging.INFO)

# 🔗 Connexion Odoo
try:
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if uid:
        logging.info(f"✅ Connecté à Odoo avec UID : {uid}")
    else:
        raise Exception("❌ Échec de connexion à Odoo")
except Exception as e:
    logging.error("❌ Erreur de connexion à Odoo", exc_info=True)
    raise e

# 🧠 Données temporaires
trajectoires = {}
timers = {}
LOCK = threading.Lock()

# 🌍 Distance Haversine
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# 🧠 Optimisation en gardant le premier point fixe
def optimize_order(points):
    if len(points) < 2:
        return points

    start_point = points[0]
    to_optimize = points[1:]
    path = [start_point]

    current = start_point
    while to_optimize:
        next_point = min(to_optimize, key=lambda p: haversine(current['lat'], current['lon'], p['lat'], p['lon']))
        path.append(next_point)
        to_optimize.remove(next_point)
        current = next_point

    path.append(start_point)
    return path

# 🚀 Finalisation d’un trajet
def finalize_trajet(trajet_key):
    with LOCK:
        points = trajectoires.get(trajet_key)
        if not points or len(points) < 2:
            logging.info(f"⚠️ Pas assez de points pour le trajet {trajet_key}")
            trajectoires.pop(trajet_key, None)
            if trajet_key in timers:
                timers.pop(trajet_key).cancel()
            return

        try:
            logging.info(f"🔄 Optimisation du trajet {trajet_key}")
            optimized = optimize_order(points)

            total_km = sum(
                haversine(optimized[i]['lat'], optimized[i]['lon'],
                          optimized[i + 1]['lat'], optimized[i + 1]['lon'])
                for i in range(len(optimized) - 1)
            )

            km_arrondi = math.ceil(total_km)
            duree_h = total_km / 60
            heures = int(duree_h)
            minutes = int((duree_h - heures) * 60)
            duree_str = f"{heures}h{minutes}min" if heures else f"{minutes}min"

            google_maps_link = "https://www.google.com/maps/dir/" + "/".join(
                f"{p['lat']},{p['lon']}" for p in optimized
            )

            nom_trajet = f"Trajet Optimisé {random.randint(100, 999)}"
            donnees = {
                'x_name': nom_trajet,
                'x_studio_distance_km': km_arrondi,
                'x_studio_dure': duree_str,
                'x_studio_nom_du_trajet': " -> ".join(p['name'] for p in optimized),
                'x_studio_coordonnes_gps': google_maps_link
            }

            record_id = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'x_trajets_optimises', 'create', [donnees]
            )
            logging.info(f"✅ Trajet {trajet_key} enregistré dans Odoo (ID {record_id})")

        except Exception as e:
            logging.error(f"❌ Erreur pendant la finalisation du trajet {trajet_key}", exc_info=True)
        finally:
            trajectoires.pop(trajet_key, None)
            if trajet_key in timers:
                timers.pop(trajet_key).cancel()

# 🧩 API de réception des points
@app.route('/optimize_route', methods=['POST'])
def optimize_route():
    try:
        data = request.json
        logging.info(f"📥 Reçu : {data}")

        trajet_key = data.get('_action') or str(uuid.uuid4())

        with LOCK:
            if trajet_key not in trajectoires:
                trajectoires[trajet_key] = []

            point = {
                'lat': float(data['x_studio_latitude']),
                'lon': float(data['x_studio_longitude']),
                'name': data.get('x_studio_nom_de_point', f"Point {len(trajectoires[trajet_key]) + 1}")
            }

            trajectoires[trajet_key].append(point)
            logging.info(f"➕ Point ajouté au trajet {trajet_key} : {point}")

            # (Re)Démarrer le timer
            if trajet_key in timers:
                timers[trajet_key].cancel()
            timer = threading.Timer(2.0, finalize_trajet, args=[trajet_key])
            timers[trajet_key] = timer
            timer.start()

        return jsonify({
            'status': 'pending',
            'trajet_key': trajet_key,
            'message': f"Point enregistré. Le trajet sera optimisé dans 2 secondes si aucun autre point n’est ajouté."
        })

    except Exception as e:
        logging.error("❌ Erreur dans /optimize_route", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ❗ Ne pas inclure app.run() ici si vous déployez avec gunicorn
