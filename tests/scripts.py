"""Shared steps for the Script and Output tests: a saved Voice and some sounds to use."""

from voices import designed_draft


def saved_voice(client, name: str = "Old Narrator") -> dict:
    """A saved Voice with the Default emotion set: neutral, angry, sad, excited."""
    response = client.post("/voices", json={"draft_id": designed_draft(client)["id"], "name": name})
    assert response.status_code == 201, response.text
    return response.json()


def add_sound(client, name: str, freesound_id: int = 101) -> dict:
    response = client.post("/sounds", json={"freesound_id": freesound_id, "name": name})
    assert response.status_code == 201, response.text
    return response.json()


def check(client, voice: dict, script: str):
    return client.post("/scripts/check", json={"voice_id": voice["id"], "script": script})
