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


def test_the_page_loads_the_shared_helpers_then_each_area(client):
    page = client.get("/").text

    order = [
        page.index(f'<script src="/static/{name}.js"></script>')
        for name in ("common", "voices", "sounds")
    ]
    assert order == sorted(order), "common.js must load before the areas that use it"
    for name, uses in [("common", "window.Voicewright"), ("sounds", "/sounds/search")]:
        script = client.get(f"/static/{name}.js")
        assert script.status_code == 200
        assert script.headers["content-type"].startswith("text/javascript")
        assert uses in script.text
