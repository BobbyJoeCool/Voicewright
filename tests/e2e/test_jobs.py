"""The job bar in the browser: one job at a time, its progress, and its errors
(spec stories 15, 48, 49)."""

from playwright.sync_api import Page, expect

from e2e.helpers import Held, area, save_voice


def test_while_a_job_runs_every_button_that_starts_one_is_disabled(vw: Page, live_app):
    save_voice(vw)
    held = Held(live_app.fakes, at_call=len(live_app.fakes.calls))
    area(vw, "scripts")
    vw.locator("#script-text").fill("One. [angry] Two. [sad] Three.")

    vw.get_by_role("button", name="Generate").click()

    expect(vw.locator("#job")).to_be_visible()
    expect(vw.locator("#job-message")).to_contain_text("(Segment 1 of 3)")
    expect(vw.locator("#script-generate")).to_be_disabled()
    area(vw, "voices")
    expect(vw.get_by_role("button", name="Design", exact=True)).to_be_disabled()
    # Starting another anyway (another tab, say) is refused.
    second = vw.request.post(f"{live_app.url}/voices/design", data={"description": "Another."})
    assert second.status == 409
    assert second.json()["detail"] == "A script job is already running; wait for it to finish"

    held.release.set()

    expect(vw.locator("#job")).to_be_hidden()
    expect(vw.get_by_role("button", name="Design", exact=True)).to_be_enabled()
    area(vw, "scripts")
    expect(vw.locator("#outputs .card")).to_have_count(1)


def test_the_progress_bar_counts_the_steps(vw: Page, live_app):
    held = Held(live_app.fakes, at_call=2)  # pause before the sad preset: step 3 of 4
    vw.locator("#design-description").fill("A calm voice.")

    vw.get_by_role("button", name="Design", exact=True).click()

    expect(vw.locator("#job-message")).to_contain_text("sad")
    expect(vw.locator("#job-progress")).to_have_attribute("max", "4")
    expect(vw.locator("#job-progress")).to_have_js_property("value", 2)
    held.release.set()
    expect(vw.locator("#job")).to_be_hidden()


def test_a_job_running_when_the_page_opens_is_followed(vw: Page, live_app):
    held = Held(live_app.fakes, at_call=1)
    vw.locator("#design-description").fill("A calm voice.")
    vw.get_by_role("button", name="Design", exact=True).click()
    expect(vw.locator("#job")).to_be_visible()

    vw.reload()

    expect(vw.locator("#job")).to_be_visible()
    expect(vw.get_by_role("button", name="Design", exact=True)).to_be_disabled()
    held.release.set()
    expect(vw.locator("#job")).to_be_hidden()
    expect(vw.locator("#drafts")).to_contain_text("A calm voice.")


def test_a_failed_job_shows_its_error_and_frees_the_page(vw: Page, live_app):
    live_app.fakes.fail_to_run["voice design"] = RuntimeError("the GPU caught fire")
    vw.locator("#design-description").fill("A calm voice.")

    vw.get_by_role("button", name="Design", exact=True).click()

    error = vw.locator('[data-error-for="design"]')
    expect(error).to_be_visible()
    expect(error).to_contain_text("the GPU caught fire")
    expect(vw.locator("#job")).to_be_hidden()
    expect(vw.get_by_role("button", name="Design", exact=True)).to_be_enabled()


def test_a_design_that_stops_part_way_keeps_what_it_made_and_can_finish(vw: Page, live_app):
    def fail_on_sad(number):
        if number == 2:
            raise RuntimeError("stopped part way")

    live_app.fakes.before_call = fail_on_sad
    vw.locator("#design-description").fill("A calm voice.")
    vw.get_by_role("button", name="Design", exact=True).click()
    expect(vw.locator('[data-error-for="design"]')).to_contain_text("stopped part way")
    live_app.fakes.before_call = None

    vw.locator("#drafts").get_by_role("button", name="Resume").click()
    review = vw.locator("#review")
    expect(review.get_by_role("button", name="Accept")).to_be_disabled()
    expect(review).to_contain_text("Design every preset before accepting.")
    for _ in range(2):  # sad, then excited
        review.get_by_role("button", name="Design it").first.click()
        expect(vw.locator("#job")).to_be_hidden()

    expect(review.get_by_role("button", name="Design it")).to_have_count(0)
    expect(review.get_by_role("button", name="Accept")).to_be_enabled()
