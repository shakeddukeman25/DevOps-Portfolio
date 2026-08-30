import os
import uuid

from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

app = Flask(__name__)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "contact_book")

mongo_client = None
db = None
people = None

if MONGO_URI:
    try:
        mongo_client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=2500,
            connectTimeoutMS=2500,
        )
        db = mongo_client[DB_NAME]
        people = db["people"]
        people.create_index([("contact_id", ASCENDING)], unique=True, sparse=True)
    except Exception:
        mongo_client = None
        db = None
        people = None


def is_mongo_available():
    if not mongo_client:
        return False
    try:
        mongo_client.admin.command("ping")
        return True
    except Exception:
        return False


def database_unavailable_response():
    return jsonify({
        "error": "MongoDB is currently unavailable",
        "message": "The website is running, but database actions are unavailable."
    }), 503


def person_to_json(person):
    return {
        "mongo_id": str(person["_id"]),
        "id": person.get("contact_id", ""),
        "name": person.get("name", ""),
        "phone": person.get("phone", ""),
        "email": person.get("email", "")
    }


def build_search_query(field, value):
    allowed_fields = {"id", "name", "phone", "email"}

    if field not in allowed_fields:
        return None

    if field == "id":
        return {"contact_id": value}

    return {field: {"$regex": value, "$options": "i"}}


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({
        "web": "ok",
        "mongodb": "connected" if is_mongo_available() else "unavailable"
    })


@app.get("/person")
def get_people():
    if not is_mongo_available():
        return database_unavailable_response()

    field = request.args.get("field", "").strip()
    value = request.args.get("value", "").strip()

    try:
        if field or value:
            if not field or not value:
                return jsonify({"error": "Both field and value are required"}), 400

            query = build_search_query(field, value)
            if query is None:
                return jsonify({
                    "error": "Invalid search field",
                    "allowed_fields": ["id", "name", "phone", "email"]
                }), 400

            result = [person_to_json(person) for person in people.find(query)]
        else:
            result = [person_to_json(person) for person in people.find()]

        return jsonify(result)
    except PyMongoError:
        return database_unavailable_response()


@app.get("/person/<contact_id>")
def get_person(contact_id):
    if not is_mongo_available():
        return database_unavailable_response()

    try:
        person = people.find_one({"contact_id": contact_id})
    except PyMongoError:
        return database_unavailable_response()

    if not person:
        return jsonify({"error": "Person not found"}), 404

    return jsonify(person_to_json(person))


@app.post("/person")
def add_person():
    if not is_mongo_available():
        return database_unavailable_response()

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    email = str(data.get("email", "")).strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400

    contact_id = str(uuid.uuid4())

    try:
        result = people.insert_one({
            "contact_id": contact_id,
            "name": name,
            "phone": phone,
            "email": email
        })

        person = people.find_one({"_id": result.inserted_id})
        return jsonify(person_to_json(person)), 201

    except DuplicateKeyError:
        return jsonify({"error": "Could not generate a unique contact ID"}), 500
    except PyMongoError:
        return database_unavailable_response()


@app.put("/person/<contact_id>")
def update_person(contact_id):
    if not is_mongo_available():
        return database_unavailable_response()

    data = request.get_json(silent=True) or {}

    updates = {}
    for field in ["name", "phone", "email"]:
        if field in data:
            updates[field] = str(data[field]).strip()

    if not updates:
        return jsonify({"error": "No fields to update"}), 400

    try:
        result = people.update_one(
            {"contact_id": contact_id},
            {"$set": updates}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Person not found"}), 404

        person = people.find_one({"contact_id": contact_id})
        return jsonify(person_to_json(person))
    except PyMongoError:
        return database_unavailable_response()


@app.delete("/person/<contact_id>")
def delete_person(contact_id):
    if not is_mongo_available():
        return database_unavailable_response()

    try:
        result = people.delete_one({"contact_id": contact_id})

        if result.deleted_count == 0:
            return jsonify({"error": "Person not found"}), 404

        return jsonify({"message": "Person deleted"})
    except PyMongoError:
        return database_unavailable_response()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
