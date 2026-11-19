"""Sounds in the browser: search the (fake) Freesound, preview, check the license, add, replace,
and remove (spec stories 26-34)."""

import wave

from playwright.sync_api import Page, expect

from e2e.helpers import add_sound, area, played, search


def test_an_empty_library_says_so(vw: Page):
    area(vw, "sounds")

    expect(vw.locator("#no-sounds")).to_be_visible()
    expect(vw.locator("#sounds .preset")).to_have_count(0)


def test_search_shows_each_result_with_its_license_and_what_it_asks(vw: Page, live_app):
    results = search(vw, "boom thunder glass")

    expect(vw.locator("#sound-search-status")).to_have_text(
        '3 results for "boom thunder glass" on Freesound.'
    )
    expect(results).to_have_count(2)
    expect(results.nth(0)).to_contain_text("Big Boom")
    expect(results.nth(0)).to_contain_text("License: Creative Commons 0. No credit needed.")
    expect(results.nth(1)).to_contain_text("License: Attribution 4.0. Credit the author.")
    assert live_app.freesound.searches == [("boom thunder glass", 1)]


def test_more_results_loads_the_next_page(vw: Page):
    results = search(vw, "boom thunder glass")
    expect(results).to_have_count(2)

    vw.get_by_role("button", name="More results").click()

    expect(results).to_have_count(3)
    expect(results.nth(2)).to_contain_text(
        "License: Attribution NonCommercial 4.0. Credit the author; not for commercial use."
    )
    expect(vw.get_by_role("button", name="More results")).to_be_hidden()


def test_a_search_with_no_hits_suggests_other_words(vw: Page):
    search(vw, "kazoo")

    expect(vw.locator("#sound-search-status")).to_have_text(
        'Nothing on Freesound for "kazoo". Try other words.'
    )


def test_a_result_can_be_previewed_before_adding(vw: Page, live_app):
    result = search(vw, "thunder").first

    assert played(vw, result.locator("audio"))
    assert live_app.freesound.downloads == [], "previewing doesn't add anything"


def test_a_result_is_offered_a_name_from_the_search(vw: Page):
    result = search(vw, "distant thunder").first

    expect(result.get_by_role("textbox")).to_have_value("distant-thunder")


def test_adding_a_result_saves_it_as_wav_with_its_credit(vw: Page, live_app):
    add_sound(vw, "thunder", "thunder")

    card = vw.locator('#sounds [data-sound="thunder"]')
    expect(card).to_contain_text("{thunder}")
    expect(card).to_contain_text('"Distant Thunder" by artist202 · Attribution 4.0')
    expect(card.get_by_role("link", name="on Freesound")).to_have_attribute(
        "href", "https://freesound.org/people/artist202/sounds/202/"
    )
    expect(vw.locator("#no-sounds")).to_be_hidden()
    expect(vw.locator("#badge-sounds")).to_have_text("1")
    assert played(vw, card.locator("audio"))
    with wave.open(str(live_app.data_folder / "sounds" / "thunder" / "sound.wav")) as stored:
        assert (stored.getnchannels(), stored.getsampwidth()) == (1, 2)


def test_a_taken_sound_name_is_refused_next_to_the_result(vw: Page):
    add_sound(vw, "thunder", "boom")
    result = search(vw, "big boom").first
    result.get_by_role("textbox").fill("boom")

    result.get_by_role("button", name="Add").click()

    expect(result.get_by_role("alert")).to_contain_text("boom")
    expect(result.get_by_role("alert")).to_be_visible()
    expect(vw.locator("#sounds .preset")).to_have_count(1)


def test_replacing_a_sound_keeps_its_name(vw: Page, live_app):
    add_sound(vw, "thunder", "boom")
    library = vw.locator('#sounds [data-sound="boom"]')

    library.get_by_role("button", name="Replace").click()
    expect(vw.locator("#sound-replacing")).to_contain_text(
        "Pick a Freesound result to replace {boom}."
    )
    replacement = search(vw, "big boom").first
    replacement.get_by_role("button", name="Replace {boom}").click()

    expect(replacement).to_contain_text("Replaced {boom} with this sound.")
    expect(vw.locator("#sound-replacing")).to_be_hidden()
    expect(library).to_contain_text('"Big Boom" by artist101')
    expect(vw.locator("#sounds .preset")).to_have_count(1)


def test_replacing_can_be_cancelled(vw: Page):
    add_sound(vw, "thunder", "boom")
    vw.locator('#sounds [data-sound="boom"]').get_by_role("button", name="Replace").click()

    vw.locator("#sound-replacing").get_by_role("button", name="Cancel").click()

    expect(vw.locator("#sound-replacing")).to_be_hidden()
    first_result = vw.locator("#sound-results .card").first
    expect(first_result.get_by_role("button", name="Add")).to_be_visible()


def test_removing_a_sound_asks_first(vw: Page):
    add_sound(vw, "thunder", "thunder")
    card = vw.locator('#sounds [data-sound="thunder"]')
    dialog = vw.locator("#confirm-dialog")

    card.get_by_role("button", name="Remove").click()
    expect(dialog.locator("#confirm-title")).to_have_text("Remove {thunder}?")
    dialog.get_by_role("button", name="Cancel").click()
    expect(card).to_be_visible()

    card.get_by_role("button", name="Remove").click()
    dialog.get_by_role("button", name="Remove").click()

    expect(vw.locator("#sounds .preset")).to_have_count(0)
    expect(vw.locator("#no-sounds")).to_be_visible()
