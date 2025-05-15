import requests
import xmlrpc.client

# Connexion à Odoo
url = 'https://agence-vo.odoo.com'
db = 'agence-vo'
username = 'bejizitouna@gmail.com'
password = 'bejizitouna2005'

common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

# Recherche des points géographiques sans coordonnées
ids = models.execute_kw(db, uid, password,
    'x_points_geographiques', 'search',
    [[['x_studio_latitude', '=', False], ['x_studio_nom_de_point', '!=', False]]])

# Traitement
for rec_id in ids:
    record = models.execute_kw(db, uid, password,
        'x_points_geographiques', 'read', [rec_id], {'fields': ['x_studio_nom_de_point']})[0]
    city = record['x_studio_nom_de_point']
    
    # Requête à OpenStreetMap (Nominatim)
    response = requests.get('https://nominatim.openstreetmap.org/search', params={
        'q': city,
        'format': 'json'
    }, headers={'User-Agent': 'OdooMapBot'})
    
    data = response.json()
    if data:
        lat = data[0]['lat']
        lon = data[0]['lon']
        # Mise à jour de l'enregistrement Odoo
        models.execute_kw(db, uid, password,
            'x_points_geographiques', 'write',
            [[rec_id], {
                'x_studio_latitude': lat,
                'x_studio_longitude': lon
            }])
        print(f"✅ {city} → {lat}, {lon}")
    else:
        print(f"❌ Coordonnées non trouvées pour : {city}")
