"""The page's layout and shell: every area fits a phone-width window, the areas are linkable,
the theme sticks, and the app can be installed (it's a PWA)."""

import pytest
from playwright.sync_api import Page, expect

from e2e.helpers import area, save_voice

AREAS = ["voices", "sounds", "scripts", "convert"]


def fits_the_width(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("width", [390, 768, 1280])
def test_every_area_fits_the_window_without_sideways_scrolling(vw: Page, width):
    vw.set_viewport_size({"width": width, "height": 844})
    save_voice(vw, "A Voice With A Fairly Long Name For A Narrow Screen")

    for name in AREAS:
        area(vw, name)
        assert fits_the_width(vw), f"{name} scrolls sideways at {width}px"


def test_each_area_has_its_own_address(vw: Page, live_app):
    for name in AREAS:
        area(vw, name)
        assert vw.url.endswith(f"#{name}")
        expect(vw.locator(".nav-item[aria-current=page]")).to_have_attribute("data-area", name)

    vw.goto(f"{live_app.url}/#sounds")
    expect(vw.locator("#area-sounds")).to_be_visible()
    expect(vw.locator("#area-title")).to_have_text("Sounds")
    vw.goto(f"{live_app.url}/#nowhere")
    expect(vw.locator("#area-voices")).to_be_visible()


def test_the_theme_toggle_sticks_across_a_reload(vw: Page):
    vw.emulate_media(color_scheme="dark")
    vw.get_by_role("button", name="Switch between light and dark").click()
    expect(vw.locator("html")).to_have_attribute("data-theme", "light")

    vw.reload()

    expect(vw.locator("html")).to_have_attribute("data-theme", "light")


def test_the_page_can_be_installed_as_an_app(vw: Page, live_app):
    manifest_href = vw.locator('link[rel="manifest"]').get_attribute("href")
    manifest = vw.request.get(live_app.url + manifest_href)

    assert manifest.ok
    data = manifest.json()
    assert data["name"].startswith("Voicewright")
    for icon in data["icons"]:
        assert vw.request.get(live_app.url + icon["src"]).ok, icon["src"]
