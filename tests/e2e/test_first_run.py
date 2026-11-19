"""The first run in the browser: an empty data folder shows an empty, inviting state in every
area, and the one setting the page offers is saved to the config file."""

from playwright.sync_api import Page, expect

from e2e.helpers import area


def test_a_fresh_data_folder_shows_every_area_empty(vw: Page):
    expect(vw).to_have_title("Voicewright")
    expect(vw.locator("#no-voices")).to_have_text("No saved Voices yet. Design one above.")
    area(vw, "sounds")
    expect(vw.locator("#no-sounds")).to_have_text("No sounds yet. Find one on Freesound below.")
    area(vw, "scripts")
    expect(vw.locator("#no-outputs")).to_be_visible()
    expect(vw.locator("#no-saved")).to_be_visible()
    for badge in ["voices", "sounds", "scripts"]:
        expect(vw.locator(f"#badge-{badge}")).to_have_text("")


def test_the_cache_size_offers_5_to_10_and_is_saved(vw: Page, live_app):
    area(vw, "scripts")
    select = vw.locator("#cache-size")
    expect(select.locator("option")).to_have_text([str(n) for n in range(5, 11)])
    expect(select).to_have_value("5")

    select.select_option("8")

    vw.wait_for_function(
        "async () => (await (await fetch('/settings')).json()).output_cache_size === 8"
    )
    assert "output_cache_size = 8" in live_app.config_path.read_text()
    vw.reload()
    expect(area(vw, "scripts").locator("#cache-size")).to_have_value("8")
