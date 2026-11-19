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
        for name in ("common", "voices", "sounds", "scripts")
    ]
    assert order == sorted(order), "common.js must load before the areas that use it"
    for name, uses in [
        ("common", "window.Voicewright"),
        ("sounds", "/sounds/search"),
        ("scripts", "/scripts/generate"),
    ]:
        script = client.get(f"/static/{name}.js")
        assert script.status_code == 200
        assert script.headers["content-type"].startswith("text/javascript")
        assert uses in script.text


def test_the_page_loads_convert_after_the_shared_helpers(client):
    page = client.get("/").text

    assert page.index('src="/static/common.js"') < page.index('src="/static/convert.js"')
    assert "/convert" in client.get("/static/convert.js").text


def test_the_page_can_be_installed_as_an_app(client):
    page = client.get("/").text
    manifest = client.get("/static/manifest.json").json()

    assert '<link rel="manifest" href="/static/manifest.json">' in page
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    for icon in manifest["icons"]:
        response = client.get(icon["src"])
        assert response.status_code == 200, icon["src"]
        assert response.headers["content-type"] == icon["type"]
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])


def test_the_page_is_styled(client):
    page = client.get("/").text
    style = client.get("/static/style.css")

    assert '<link rel="stylesheet" href="/static/style.css">' in page
    assert style.status_code == 200
    assert style.headers["content-type"].startswith("text/css")


def test_confirmations_use_the_page_dialog_not_the_browser_box(client):
    page = client.get("/").text

    assert '<dialog id="confirm-dialog"' in page
    for name in ("common", "voices", "sounds", "scripts", "convert"):
        script = client.get(f"/static/{name}.js").text
        for box in ("alert(", "prompt(", "window.confirm("):
            assert box not in script, f"{name}.js uses the browser's {box}) box"
        # Every confirm() call goes through the page's dialog: Voicewright.confirm, awaited.
        code = (line for line in script.splitlines() if not line.strip().startswith("//"))
        for line in code:
            if "confirm(" in line and "function confirmAction" not in line:
                assert "await confirm(" in line, f"{name}.js: {line.strip()}"
