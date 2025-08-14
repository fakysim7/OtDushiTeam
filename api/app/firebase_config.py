# import firebase_admin
# from firebase_admin import credentials, db

# cred = credentials.Certificate("D:/work/bots/reservation_service/ai-bot-id-firebase-adminsdk-fbsvc-67ad9fc596.json")

# firebase_admin.initialize_app(cred, {
#     'databaseURL': ''
# })

# import firebase_admin
# from firebase_admin import credentials, db

# cred = credentials.Certificate("ai-bot-id-firebase-adminsdk-fbsvc-67ad9fc596.json")
# firebase_admin.initialize_app(cred, {
#     'databaseURL': 'https://ai-bot-id-default-rtdb.firebaseio.com'
# })

# # Создаем ссылку на базу данных
# ref = db.reference('/reservations')

import os
import json
import firebase_admin
from firebase_admin import credentials, db

firebase_credentials_json = os.getenv('FIREBASE_CREDENTIALS_JSON')
if not firebase_credentials_json:
    raise RuntimeError("FIREBASE_CREDENTIALS_JSON not set")

# Парсим строку JSON
cred_data = json.loads(firebase_credentials_json)

cred = credentials.Certificate(cred_data)

firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv('FIREBASE_DATABASE_URL')
})

ref = db.reference('reservations')
