"""Errors in the browser: each one is a plain sentence where the user is looking, and the rest of
the app keeps working (spec stories 35 and 60)."""

from fakes import load_error
from playwright.sync_api import Page, expect

from e2e.helpers import add_sound, area, save_voice
from voicewright.freesound import NO_API_KEY, FreesoundUnavailable


def test_a_model_that_is_not_installed_is_reported_plainly(vw: Page, live_app):
    live_app.fakes.fail_to_load["voice design"] = load_error(
        "voice design model", "the weights aren't downloaded"
    )
    vw.locator("#design-description").fill("A calm voice.")

    vw.get_by_role("button", name="Design", exact=True).click()

    expect(vw.locator('[data-error-for="design"]')).to_have_text(
        "The voice design job stopped: couldn't load the voice design model: "
        "the weights aren't downloaded."
    )
    # What was typed stays, so the user can try again once the model is there.
    del live_app.fakes.fail_to_load["voice design"]
    vw.get_by_role("button", name="Design", exact=True).click()
    expect(vw.locator("#review")).to_be_visible()


def test_a_missing_freesound_key_explains_how_to_get_one(vw: Page, live_app):
    live_app.freesound.unavailable = FreesoundUnavailable(
        NO_API_KEY, "searching Freesound needs an API key"
    )
    area(vw, "sounds")
    vw.locator("#sound-query").fill("thunder")

    vw.get_by_role("button", name="Search").click()

    error = vw.locator("#sound-search-error")
    expect(error).to_contain_text("Searching Freesound needs an API key.")
    expect(error.get_by_role("link", name="Get a Freesound API key")).to_have_attribute(
        "href", "https://freesound.org/apiv2/apply"
    )
    expect(vw.locator("#sound-search-status")).to_have_text("")


def test_freesound_being_down_leaves_the_rest_of_the_app_working(vw: Page, live_app):
    add_sound(vw, "thunder", "thunder")
    live_app.freesound.unavailable = FreesoundUnavailable("unreachable", "can't reach Freesound")
    vw.locator("#sound-query").fill("boom")
    vw.get_by_role("button", name="Search").click()
    expect(vw.locator("#sound-search-error")).to_have_text("Can't reach Freesound.")

    save_voice(vw)
    area(vw, "scripts")
    vw.locator("#script-text").fill("Still works. {thunder}")
    vw.get_by_role("button", name="Generate").click()

    expect(vw.locator("#outputs .card")).to_have_count(1)


def test_losing_the_app_says_so_instead_of_failing_silently(vw: Page):
    vw.route("**/voices/design", lambda route: route.abort())
    vw.locator("#design-description").fill("A calm voice.")

    vw.get_by_role("button", name="Design", exact=True).click()

    expect(vw.locator('[data-error-for="design"]')).to_have_text(
        "Can't reach Voicewright; is it still running?"
    )
    expect(vw.get_by_role("button", name="Design", exact=True)).to_be_enabled()


def test_a_server_error_with_no_detail_still_reads_as_a_sentence(vw: Page):
    vw.route(
        "**/voices/design",
        lambda route: route.fulfill(status=500, body="oops", content_type="text/plain"),
    )
    vw.locator("#design-description").fill("A calm voice.")

    vw.get_by_role("button", name="Design", exact=True).click()

    expect(vw.locator('[data-error-for="design"]')).to_have_text("Something went wrong (HTTP 500).")
