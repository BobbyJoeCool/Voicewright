def test_home_serves_the_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Voicewright</title>" in response.text


def test_the_page_loads_the_voices_script(client):
    page = client.get("/").text
    script = client.get("/static/voices.js")

    assert '<script src="/static/voices.js"></script>' in page
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")
    assert "/voices/design" in script.text
