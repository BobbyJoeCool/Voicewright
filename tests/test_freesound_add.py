import io
import wave

import pytest

from voicewright.freesound import BAD_API_KEY, NO_API_KEY, UNREACHABLE, FreesoundUnavailable


def add(client, freesound_id: int = 101, name: str = "explosion"):
    return client.post("/sounds", json={"freesound_id": freesound_id, "name": name})


def test_search_returns_previews_and_licenses(client, freesound):
    response = client.get("/sounds/search", params={"q": "  boom  "})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    [result] = body["results"]
    assert result == {
        "id": 101,
        "title": "Big Boom",
        "author": "artist101",
        "license": "Creative Commons 0",
        "url": "https://freesound.org/people/artist101/sounds/101/",
        "duration": 0.5,
        "preview_url": "https://cdn.freesound.org/previews/101-hq.ogg",
    }
    assert freesound.searches == [("boom", 1)], "the query is trimmed"


def test_search_pages_through_results(client):
    first = client.get("/sounds/search", params={"q": "big distant glass"}).json()
    second = client.get("/sounds/search", params={"q": "big distant glass", "page": 2}).json()

    assert (first["count"], first["page"], first["has_next"]) == (3, 1, True)
    assert [r["title"] for r in first["results"]] == ["Big Boom", "Distant Thunder"]
    assert (second["page"], second["has_next"]) == (2, False)
    assert [r["title"] for r in second["results"]] == ["Glass Break"]


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "   "}, {"q": "boom", "page": 0}])
def test_a_bad_search_is_refused(client, freesound, params):
    response = client.get("/sounds/search", params=params)

    assert response.status_code == 422
    assert freesound.searches == []


def test_adding_a_non_wav_result_stores_standard_wav_with_its_license(client, freesound):
    assert freesound.audio[:4] == b"OggS", "the fake downloads OGG, so the converter runs"

    response = add(client, 202, "thunder")

    assert response.status_code == 201, response.text
    sound = response.json()
    assert sound["name"] == "thunder"
    assert sound["credit"] == {
        "title": "Distant Thunder",
        "author": "artist202",
        "license": "Attribution 4.0",
        "source": "https://freesound.org/people/artist202/sounds/202/",
        "attribution": '"Distant Thunder" by artist202 '
        "(https://freesound.org/people/artist202/sounds/202/), licensed under Attribution 4.0",
        "freesound_id": 202,
    }
    assert sound["duration"] == pytest.approx(0.5, abs=0.1)
    audio = client.get(sound["audio_url"])
    assert audio.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(audio.content)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) == (1, 2, "NONE")
    assert client.get("/sounds").json() == [sound]
    assert freesound.downloads == [202]


def test_the_chosen_name_is_lowercased(client):
    response = add(client, 101, "  Big-Boom ")

    assert response.json()["name"] == "big-boom"
    assert client.get("/sounds/BIG-BOOM/audio").status_code == 200


def test_adding_under_a_taken_name_is_refused_before_downloading(client, freesound):
    add(client, 101, "explosion")

    response = add(client, 202, "EXPLOSION")

    assert response.status_code == 409
    assert "already has {explosion}" in response.json()["detail"]
    assert freesound.downloads == [101]
    assert client.get("/sounds").json()[0]["credit"]["freesound_id"] == 101


@pytest.mark.parametrize("name", ["door slam", "", "-x", "a" * 61])
def test_adding_under_a_bad_name_is_refused_before_downloading(client, freesound, name):
    response = add(client, 101, name)

    assert response.status_code == 422
    assert "can't be a sound name" in response.json()["detail"][0]["msg"]
    assert freesound.downloads == []


@pytest.mark.parametrize("freesound_id", [0, -1])
def test_a_bad_freesound_id_is_refused(client, freesound_id):
    assert add(client, freesound_id).status_code == 422


def test_adding_a_sound_freesound_doesnt_have_is_404(client):
    response = add(client, 999)

    assert response.status_code == 404
    assert "no sound 999" in response.json()["detail"]
    assert client.get("/sounds").json() == []


def test_a_download_that_isnt_audio_is_refused_and_nothing_is_stored(client, freesound):
    freesound.audio = b"<html>not a sound</html>"

    response = add(client)

    assert response.status_code == 502
    assert "Big Boom" in response.json()["detail"]
    assert client.get("/sounds").json() == []


def test_replace_keeps_the_name_and_takes_the_new_sound_and_credit(client, freesound):
    add(client, 101, "explosion")

    response = client.put("/sounds/Explosion", json={"freesound_id": 303})

    assert response.status_code == 200, response.text
    [sound] = client.get("/sounds").json()
    assert sound == response.json()
    assert sound["name"] == "explosion"
    assert sound["credit"]["title"] == "Glass Break"
    assert sound["credit"]["license"] == "Attribution NonCommercial 4.0"
    assert freesound.downloads == [101, 303]


def test_replacing_a_name_that_isnt_there_is_404_before_downloading(client, freesound):
    response = client.put("/sounds/explosion", json={"freesound_id": 101})

    assert response.status_code == 404
    assert freesound.downloads == []


@pytest.mark.parametrize("reason", [NO_API_KEY, UNREACHABLE, BAD_API_KEY])
def test_freesound_trouble_is_503_with_its_reason_and_the_rest_still_works(
    client, freesound, reason
):
    add(client, 101, "explosion")
    freesound.unavailable = FreesoundUnavailable(reason, f"Freesound trouble: {reason}")

    calls = [
        client.get("/sounds/search", params={"q": "boom"}),
        add(client, 202, "thunder"),
        client.put("/sounds/explosion", json={"freesound_id": 202}),
    ]

    for response in calls:
        assert response.status_code == 503
        assert response.json() == {"detail": f"Freesound trouble: {reason}", "reason": reason}
    [sound] = client.get("/sounds").json()
    assert sound["credit"]["freesound_id"] == 101, "a failed replace leaves the sound alone"
    assert client.get(sound["audio_url"]).status_code == 200
    assert client.get("/voices").status_code == 200
    assert client.get("/").status_code == 200
