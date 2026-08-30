import requests
import time


# ------------------------------------------------------------
# Base URL
# ------------------------------------------------------------
# The tests communicate with the application through Nginx.
#
# Docker Compose exposes Nginx on port 80, therefore the API
# is available through:
#
#     http://localhost
#
# We are NOT using Flask test_client here.
# These are real HTTP requests to the running containers.
# ------------------------------------------------------------

BASE_URL = "http://localhost"


def wait_for_application():
    """
    Wait until the Flask application is ready.

    Docker containers may need a few seconds to start.

    Instead of immediately running the tests, we try the
    /health endpoint several times.

    If the application becomes available, the function returns.

    If it never becomes available, the integration test fails.
    """

    for attempt in range(15):

        try:
            response = requests.get(
                f"{BASE_URL}/health",
                timeout=3
            )

            if response.status_code == 200:
                return

        except requests.RequestException:
            pass

        time.sleep(2)

    raise RuntimeError(
        "Application did not become ready"
    )


# ============================================================
# Integration Tests
# ============================================================


def test_health():
    """
    Verify that the web application is running
    and MongoDB is connected.

    This tests real communication:

        Test
          ->
        Nginx
          ->
        Flask
          ->
        MongoDB
    """

    wait_for_application()

    response = requests.get(
        f"{BASE_URL}/health"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["web"] == "ok"

    # For the integration environment MongoDB should actually
    # be running through Docker Compose.
    assert data["mongodb"] == "connected"


def test_create_and_get_contact():
    """
    Full integration scenario.

    1. POST a new contact.
    2. Read the generated contact ID.
    3. GET the same contact from the API.
    4. Verify that the data was really stored.
    5. DELETE the contact after the test.

    Unlike unit tests, MongoDB is real here.
    """

    # --------------------------------------------------------
    # STEP 1 - Create contact
    # --------------------------------------------------------

    new_contact = {
        "name": "Integration Test User",
        "phone": "0501234567",
        "email": "integration@test.com"
    }

    create_response = requests.post(
        f"{BASE_URL}/person",
        json=new_contact
    )

    assert create_response.status_code == 201

    created_contact = create_response.json()

    # The application should create a UUID automatically.
    assert "id" in created_contact

    contact_id = created_contact["id"]

    assert created_contact["name"] == "Integration Test User"
    assert created_contact["phone"] == "0501234567"
    assert created_contact["email"] == "integration@test.com"


    # --------------------------------------------------------
    # STEP 2 - GET the contact from MongoDB
    # --------------------------------------------------------

    get_response = requests.get(
        f"{BASE_URL}/person/{contact_id}"
    )

    assert get_response.status_code == 200

    saved_contact = get_response.json()

    assert saved_contact["id"] == contact_id
    assert saved_contact["name"] == "Integration Test User"
    assert saved_contact["phone"] == "0501234567"
    assert saved_contact["email"] == "integration@test.com"


    # --------------------------------------------------------
    # STEP 3 - Cleanup
    # --------------------------------------------------------
    # Remove the contact created by this test so that the
    # integration test does not leave unnecessary data behind.
    # --------------------------------------------------------

    delete_response = requests.delete(
        f"{BASE_URL}/person/{contact_id}"
    )

    assert delete_response.status_code == 200


def test_get_all_contacts():
    """
    Verify that GET /person works against the real MongoDB.

    The response should be a JSON list.
    """

    response = requests.get(
        f"{BASE_URL}/person"
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)


def test_search_contact():
    """
    Test the search API against the real application
    and real MongoDB.

    The test:
    1. Creates a contact.
    2. Searches for it by name.
    3. Verifies that it is found.
    4. Deletes it afterward.
    """

    contact = {
        "name": "Integration Search User",
        "phone": "0508888888",
        "email": "search@test.com"
    }

    # Create test data
    create_response = requests.post(
        f"{BASE_URL}/person",
        json=contact
    )

    assert create_response.status_code == 201

    contact_id = create_response.json()["id"]


    # Search through the real REST API
    search_response = requests.get(
        f"{BASE_URL}/person",
        params={
            "field": "name",
            "value": "Integration Search"
        }
    )

    assert search_response.status_code == 200

    results = search_response.json()

    assert len(results) >= 1

    assert any(
        person["id"] == contact_id
        for person in results
    )


    # Cleanup
    delete_response = requests.delete(
        f"{BASE_URL}/person/{contact_id}"
    )

    assert delete_response.status_code == 200