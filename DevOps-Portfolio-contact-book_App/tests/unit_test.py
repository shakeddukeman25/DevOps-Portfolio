import os
import sys

# ------------------------------------------------------------
# Make the project root importable
# ------------------------------------------------------------
# unit_test.py is inside the tests/ directory, while app.py is
# located one directory above it.
#
# This line adds the project root directory to Python's module
# search path so that:
#
#     import app as contact_app
#
# works both locally and inside GitHub Actions.
# ------------------------------------------------------------
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
)


import pytest
from unittest.mock import MagicMock
from bson.objectid import ObjectId
from prometheus_client import REGISTRY

import app as contact_app


# ============================================================
# Prometheus cleanup
# ============================================================

def clear_prometheus_registry():
    """
    Remove all registered Prometheus collectors.

    Why do we need this?

    When pytest imports the Flask application several times,
    Prometheus metrics may be registered more than once.

    Without cleanup, this may cause errors such as:

        ValueError: Duplicated timeseries in CollectorRegistry

    The tests themselves do not depend on Prometheus,
    but cleaning the registry makes the test environment safer.
    """

    collectors = list(REGISTRY._collector_to_names.keys())

    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass


# ============================================================
# Pytest Fixture
# ============================================================

@pytest.fixture
def client(mocker):
    """
    Prepare the Flask application for every unit test.

    This fixture does four main things:

    1. Clears Prometheus state.
    2. Creates a fake MongoDB collection.
    3. Replaces the real MongoDB connection with a mock.
    4. Creates a Flask test client.

    The important idea:

        We do NOT connect to a real MongoDB server.

    Instead, we simulate MongoDB using MagicMock.

    This means the unit tests can run:
    - locally
    - inside GitHub Actions
    - without Docker
    - without MongoDB
    """

    # Clean previous Prometheus collectors before each test.
    clear_prometheus_registry()


    # --------------------------------------------------------
    # Create fake MongoDB collection
    # --------------------------------------------------------

    mock_people_collection = MagicMock()

    """
    Our real application normally uses:

        people.find()
        people.find_one()
        people.insert_one()
        people.update_one()
        people.delete_one()

    During unit tests, all of these calls will go to this
    MagicMock instead of a real MongoDB collection.
    """


    # --------------------------------------------------------
    # Pretend MongoDB is available
    # --------------------------------------------------------

    mocker.patch.object(
        contact_app,
        "is_mongo_available",
        return_value=True
    )

    """
    Most endpoints in app.py first check:

        if not is_mongo_available():
            ...

    For the normal tests we want the application to continue
    as if MongoDB is online.

    Therefore we replace is_mongo_available() with a function
    that always returns True.
    """


    # --------------------------------------------------------
    # Replace the real MongoDB collection
    # --------------------------------------------------------

    mocker.patch.object(
        contact_app,
        "people",
        mock_people_collection
    )

    """
    From this point on:

        contact_app.people.find()

    actually means:

        mock_people_collection.find()

    No real database request is sent.
    """


    # --------------------------------------------------------
    # Fake contacts stored in MongoDB
    # --------------------------------------------------------

    mock_people = [
        {
            "_id": ObjectId("60c72b2f9b1d8f001c8e4d2a"),
            "contact_id": "user-001",
            "name": "John Doe",
            "phone": "0501111111",
            "email": "john@example.com"
        },
        {
            "_id": ObjectId("60c72b2f9b1d8f001c8e4d2b"),
            "contact_id": "user-002",
            "name": "Alice Smith",
            "phone": "0502222222",
            "email": "alice@example.com"
        }
    ]

    """
    These contacts are fake test data.

    They allow us to know exactly what the API should return.

    This makes the tests deterministic:
    the result is always the same.
    """


    # --------------------------------------------------------
    # Mock GET /person
    # --------------------------------------------------------

    mock_people_collection.find.return_value = mock_people

    """
    When app.py calls:

        people.find()

    the mock returns the two contacts above.
    """


    # --------------------------------------------------------
    # Mock find_one()
    # --------------------------------------------------------

    def mock_find_one(query):
        """
        Simulate MongoDB find_one() behavior.

        Different queries return different fake contacts.
        """

        # GET /person/user-001
        if query == {"contact_id": "user-001"}:
            return mock_people[0]

        # GET /person/user-002
        if query == {"contact_id": "user-002"}:
            return mock_people[1]

        # Used after POST /person.
        #
        # After inserting a new contact, the real application
        # searches MongoDB again using the inserted MongoDB _id.
        if query == {
            "_id": ObjectId("60c72b2f9b1d8f001c8e4d99")
        }:
            return {
                "_id": ObjectId("60c72b2f9b1d8f001c8e4d99"),
                "contact_id": "test-generated-uuid",
                "name": "New Contact",
                "phone": "0503333333",
                "email": "new@example.com"
            }

        # Simulates a contact that does not exist.
        return None


    mock_people_collection.find_one.side_effect = mock_find_one


    # --------------------------------------------------------
    # Mock insert_one()
    # --------------------------------------------------------

    mock_people_collection.insert_one.return_value = MagicMock(
        inserted_id=ObjectId("60c72b2f9b1d8f001c8e4d99")
    )

    """
    Real MongoDB returns an object containing inserted_id.

    We simulate exactly that behavior.
    """


    # --------------------------------------------------------
    # Mock update_one()
    # --------------------------------------------------------

    mock_people_collection.update_one.return_value = MagicMock(
        matched_count=1,
        modified_count=1
    )

    """
    matched_count=1 means:
        MongoDB found the contact.

    modified_count=1 means:
        MongoDB successfully changed the document.
    """


    # --------------------------------------------------------
    # Mock delete_one()
    # --------------------------------------------------------

    mock_people_collection.delete_one.return_value = MagicMock(
        deleted_count=1
    )

    """
    deleted_count=1 means:
        MongoDB successfully deleted one contact.
    """


    # --------------------------------------------------------
    # Enable Flask testing mode
    # --------------------------------------------------------

    contact_app.app.config["TESTING"] = True

    """
    Flask provides a built-in test client.

    It allows us to make requests such as:

        client.get("/")
        client.post("/person")
        client.put("/person/user-001")
        client.delete("/person/user-001")

    without starting:

        python app.py

    and without opening port 5000.
    """


    with contact_app.app.test_client() as client:
        yield client


# ============================================================
# Unit Tests
# ============================================================


def test_index_page(client):
    """
    Test the main web page.

    Endpoint:
        GET /

    We verify:
    1. The server returns HTTP 200.
    2. Important HTML text exists on the page.
    """

    response = client.get("/")

    assert response.status_code == 200

    assert b"Contact Book" in response.data
    assert b"Add Contact" in response.data
    assert b"Search Contacts" in response.data


def test_health_endpoint(client):
    """
    Test the health endpoint.

    Endpoint:
        GET /health

    Because the fixture mocks MongoDB as available,
    we expect:

        web = ok
        mongodb = connected
    """

    response = client.get("/health")

    assert response.status_code == 200

    data = response.get_json()

    assert data["web"] == "ok"
    assert data["mongodb"] == "connected"


def test_get_all_people(client):
    """
    Test retrieving all contacts.

    Endpoint:
        GET /person

    The mocked MongoDB find() returns two contacts.

    We verify:
    - HTTP 200
    - two contacts are returned
    - the data is correct
    """

    response = client.get("/person")

    assert response.status_code == 200

    data = response.get_json()

    assert len(data) == 2

    assert data[0]["id"] == "user-001"
    assert data[0]["name"] == "John Doe"

    assert data[1]["id"] == "user-002"
    assert data[1]["name"] == "Alice Smith"


def test_get_existing_person(client):
    """
    Test retrieving one contact by its application UUID.

    Endpoint:
        GET /person/<id>

    Example:
        GET /person/user-001
    """

    response = client.get("/person/user-001")

    assert response.status_code == 200

    data = response.get_json()

    assert data["id"] == "user-001"
    assert data["name"] == "John Doe"
    assert data["phone"] == "0501111111"
    assert data["email"] == "john@example.com"


def test_get_non_existent_person(client):
    """
    Test requesting a contact that does not exist.

    Expected behavior:
        HTTP 404
        Person not found
    """

    response = client.get("/person/user-999")

    assert response.status_code == 404

    data = response.get_json()

    assert data["error"] == "Person not found"


def test_search_person_by_name(client):
    """
    Test search by name.

    Endpoint:
        GET /person?field=name&value=John

    The test checks two things:

    1. The REST API returns the expected result.
    2. The backend builds the correct MongoDB query.
    """

    contact_app.people.find.return_value = [
        {
            "_id": ObjectId("60c72b2f9b1d8f001c8e4d2a"),
            "contact_id": "user-001",
            "name": "John Doe",
            "phone": "0501111111",
            "email": "john@example.com"
        }
    ]

    response = client.get(
        "/person?field=name&value=John"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert len(data) == 1
    assert data[0]["name"] == "John Doe"


    # Verify the MongoDB query created by app.py.
    contact_app.people.find.assert_called_with(
        {
            "name": {
                "$regex": "John",
                "$options": "i"
            }
        }
    )


def test_search_person_by_email(client):
    """
    Test search by email.

    Endpoint:
        GET /person?field=email&value=alice
    """

    contact_app.people.find.return_value = [
        {
            "_id": ObjectId("60c72b2f9b1d8f001c8e4d2b"),
            "contact_id": "user-002",
            "name": "Alice Smith",
            "phone": "0502222222",
            "email": "alice@example.com"
        }
    ]

    response = client.get(
        "/person?field=email&value=alice"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert len(data) == 1
    assert data[0]["email"] == "alice@example.com"


def test_search_invalid_field(client):
    """
    Test searching with a field that is not allowed.

    Example:
        GET /person?field=address&value=London

    The API only supports:
        id
        name
        phone
        email

    Expected:
        HTTP 400
    """

    response = client.get(
        "/person?field=address&value=London"
    )

    assert response.status_code == 400

    data = response.get_json()

    assert data["error"] == "Invalid search field"


def test_create_person_success(client, mocker):
    """
    Test creating a new contact.

    Endpoint:
        POST /person

    The application normally generates a random UUID.

    A random value would make the unit test unpredictable,
    so we mock uuid.uuid4() and force it to return:

        test-generated-uuid
    """

    fake_uuid = MagicMock()

    fake_uuid.__str__.return_value = "test-generated-uuid"


    # Replace uuid.uuid4() temporarily.
    mocker.patch.object(
        contact_app.uuid,
        "uuid4",
        return_value=fake_uuid
    )


    response = client.post(
        "/person",
        json={
            "name": "New Contact",
            "phone": "0503333333",
            "email": "new@example.com"
        }
    )


    assert response.status_code == 201

    data = response.get_json()

    assert data["id"] == "test-generated-uuid"
    assert data["name"] == "New Contact"
    assert data["phone"] == "0503333333"
    assert data["email"] == "new@example.com"


    # Verify exactly what the application attempted
    # to insert into MongoDB.
    contact_app.people.insert_one.assert_called_once_with(
        {
            "contact_id": "test-generated-uuid",
            "name": "New Contact",
            "phone": "0503333333",
            "email": "new@example.com"
        }
    )


def test_create_person_missing_name(client):
    """
    Test validation when creating a contact.

    Name is required.

    Expected:
        HTTP 400
        Name is required
    """

    response = client.post(
        "/person",
        json={
            "name": "",
            "phone": "0503333333",
            "email": "new@example.com"
        }
    )

    assert response.status_code == 400

    data = response.get_json()

    assert data["error"] == "Name is required"


def test_update_person_success(client):
    """
    Test updating an existing contact.

    Endpoint:
        PUT /person/user-001

    The fake MongoDB update result says:

        matched_count = 1

    which means the contact exists.
    """

    # The fixture originally uses side_effect for find_one().
    # For this test we want to return the updated contact
    # directly, so we disable the side_effect.
    contact_app.people.find_one.side_effect = None

    contact_app.people.find_one.return_value = {
        "_id": ObjectId("60c72b2f9b1d8f001c8e4d2a"),
        "contact_id": "user-001",
        "name": "John Updated",
        "phone": "0509999999",
        "email": "updated@example.com"
    }


    response = client.put(
        "/person/user-001",
        json={
            "name": "John Updated",
            "phone": "0509999999",
            "email": "updated@example.com"
        }
    )


    assert response.status_code == 200

    data = response.get_json()

    assert data["name"] == "John Updated"
    assert data["phone"] == "0509999999"


    # Verify that the correct MongoDB update was attempted.
    contact_app.people.update_one.assert_called_once_with(
        {"contact_id": "user-001"},
        {
            "$set": {
                "name": "John Updated",
                "phone": "0509999999",
                "email": "updated@example.com"
            }
        }
    )


def test_update_non_existent_person(client):
    """
    Test updating a contact that does not exist.

    matched_count=0 simulates MongoDB not finding the contact.

    Expected:
        HTTP 404
    """

    contact_app.people.update_one.return_value = MagicMock(
        matched_count=0,
        modified_count=0
    )

    response = client.put(
        "/person/user-999",
        json={
            "name": "Unknown Person"
        }
    )

    assert response.status_code == 404

    data = response.get_json()

    assert data["error"] == "Person not found"


def test_delete_person_success(client):
    """
    Test deleting an existing contact.

    Endpoint:
        DELETE /person/user-001

    The fixture returns:

        deleted_count = 1

    which simulates a successful MongoDB delete.
    """

    response = client.delete(
        "/person/user-001"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["message"] == "Person deleted"


    # Verify that the application used the correct ID.
    contact_app.people.delete_one.assert_called_once_with(
        {"contact_id": "user-001"}
    )


def test_delete_non_existent_person(client):
    """
    Test deleting a contact that does not exist.

    deleted_count=0 simulates MongoDB finding nothing.

    Expected:
        HTTP 404
    """

    contact_app.people.delete_one.return_value = MagicMock(
        deleted_count=0
    )

    response = client.delete(
        "/person/user-999"
    )

    assert response.status_code == 404

    data = response.get_json()

    assert data["error"] == "Person not found"


def test_mongodb_unavailable(client, mocker):
    """
    Test application behavior when MongoDB is down.

    This is important for our application because the design
    requires the website to stay alive even if MongoDB fails.

    For this test we change:

        is_mongo_available()

    from True to False.

    Expected:
        GET /person
        -> HTTP 503 Service Unavailable
    """

    mocker.patch.object(
        contact_app,
        "is_mongo_available",
        return_value=False
    )

    response = client.get("/person")

    assert response.status_code == 503

    data = response.get_json()

    assert data["error"] == "MongoDB is currently unavailable"