"""Voices in the browser: design, review, retune, roll back, accept, edit, delete, and discard
(spec stories 1-25)."""

import re

from playwright.sync_api import Page, expect

from e2e.helpers import Held, area, design_voice, played, save_voice

EMOTIONS = ["neutral", "angry", "sad", "excited"]


def preset(review, emotion: str):
    """One preset's block in the Draft review."""
    heading = "neutral (the Voice's identity)" if emotion == "neutral" else emotion
    return review.locator(".preset").filter(
        has=review.page.locator("strong").get_by_text(heading, exact=True)
    )


def saved_preset(card, emotion: str):
    """One preset's block in a saved Voice's card."""
    return card.locator("div.preset").filter(
        has=card.page.locator("strong").get_by_text(emotion, exact=True)
    )


def test_an_empty_data_folder_offers_to_design_the_first_voice(vw: Page):
    expect(vw.locator("#area-title")).to_have_text("Voices")
    expect(vw.locator("#no-voices")).to_be_visible()
    expect(vw.locator("#drafts-area")).to_be_hidden()
    expect(vw.locator("#review")).to_be_hidden()
    expect(vw.locator("#badge-voices")).to_have_text("")


def test_a_described_voice_is_designed_with_every_default_emotion(vw: Page, live_app):
    review = design_voice(vw, "A gravelly older man, slow and calm.")

    for emotion in EMOTIONS:
        expect(preset(review, emotion).locator("audio")).to_have_count(1)
    assert played(vw, preset(review, "neutral").locator("audio").first)
    # The design form is cleared, and the draft is listed to resume later.
    expect(vw.locator("#design-description")).to_have_value("")
    expect(vw.locator("#drafts")).to_contain_text("A gravelly older man, slow and calm.")
    designed = [c.inputs["emotion"] for c in live_app.fakes.calls if c.model == "voice design"]
    assert designed == [None, "angry", "sad", "excited"]


def test_a_blank_description_is_refused_by_the_form(vw: Page, live_app):
    vw.locator("#design-description").fill("   ")
    vw.get_by_role("button", name="Design", exact=True).click()

    expect(vw.locator('[data-error-for="design"]')).to_have_text(
        "Describe the voice, e.g. a gravelly older man, slow and calm."
    )
    assert live_app.fakes.calls == []


def test_regenerating_one_preset_adds_a_take_and_leaves_the_others(vw: Page, live_app):
    review = design_voice(vw)
    calls_before = len(live_app.fakes.calls)

    preset(review, "angry").get_by_role("button", name="Regenerate").click()

    takes = preset(review, "angry").locator("select")
    expect(takes.locator("option")).to_have_count(2)
    expect(takes).to_have_value("angry-2")
    new_calls = live_app.fakes.calls[calls_before:]
    assert [c.inputs["emotion"] for c in new_calls] == ["angry"]
    expect(preset(review, "sad").locator("select")).to_have_count(0)


def test_a_draft_neutral_clip_can_be_regenerated(vw: Page, live_app):
    review = design_voice(vw)

    preset(review, "neutral").get_by_role("button", name="Regenerate the neutral clip").click()

    expect(preset(review, "neutral").locator("select")).to_have_value("neutral-2")
    assert live_app.fakes.calls[-1].inputs["emotion"] is None


def test_going_back_to_an_earlier_take(vw: Page):
    review = design_voice(vw)
    preset(review, "angry").get_by_role("button", name="Regenerate").click()
    takes = preset(review, "angry").locator("select")
    expect(takes).to_have_value("angry-2")

    takes.select_option("angry-1")

    expect(preset(review, "angry").locator("select")).to_have_value("angry-1")
    expect(preset(review, "angry").locator("audio").first).to_have_attribute(
        "src", re.compile(r"/takes/angry-1$")
    )


def test_retuning_a_preset_speaks_it_at_the_chosen_values(vw: Page, live_app):
    review = design_voice(vw)
    sad = preset(review, "sad")
    sliders = sad.locator('input[type="range"]')
    sliders.nth(0).fill("0.9")
    sliders.nth(1).fill("0.2")
    expect(sad.locator("output").nth(0)).to_have_text("0.90")

    sad.get_by_role("button", name="Hear these values").click()

    expect(preset(review, "sad")).to_contain_text("Spoken at exaggeration 0.9, cfg 0.2:")
    speech = [c for c in live_app.fakes.calls if c.model == "speech"]
    assert (speech[-1].inputs["exaggeration"], speech[-1].inputs["cfg"]) == (0.9, 0.2)


def test_editing_the_description_redesigns_every_preset(vw: Page, live_app):
    review = design_voice(vw, "A calm voice.")
    review.locator("textarea").fill("A calm voice, a little hoarse.")

    review.get_by_role("button", name="Redesign every preset from this description").click()

    expect(preset(review, "excited").locator("select option")).to_have_count(2)
    redesigned = [c.inputs["description"] for c in live_app.fakes.calls[-4:]]
    assert redesigned == ["A calm voice, a little hoarse."] * 4
    expect(vw.locator("#drafts")).to_contain_text("A calm voice, a little hoarse.")


def test_accepting_saves_the_voice_with_its_presets(vw: Page):
    card = save_voice(vw, "QA Narrator")

    expect(vw.locator("#review")).to_be_hidden()
    expect(vw.locator("#drafts-area")).to_be_hidden()
    expect(vw.locator("#no-voices")).to_be_hidden()
    expect(vw.locator("#badge-voices")).to_have_text("1")
    expect(card.locator(".chip.emotion")).to_have_text(EMOTIONS)
    card.locator("summary").click()
    expect(card.locator(".preset audio")).to_have_count(4)
    assert played(vw, card.locator(".preset audio").first)


def test_a_taken_name_is_refused_and_the_draft_stays(vw: Page):
    save_voice(vw, "QA Narrator")
    review = design_voice(vw, "A bright young voice.")
    review.get_by_placeholder("Old Narrator").fill("qa narrator")

    review.get_by_role("button", name="Accept").click()

    expect(review.locator('[data-error-for^="accept-"]')).to_have_text(
        "A Voice named QA Narrator already exists; pick another name."
    )
    expect(review.get_by_placeholder("Old Narrator")).to_have_value("qa narrator")
    expect(vw.locator("#voices details.card")).to_have_count(1)


def test_a_saved_voice_neutral_clip_is_locked(vw: Page):
    card = save_voice(vw)
    card.locator("summary").click()
    neutral = card.locator(".preset").filter(
        has=vw.locator("strong").get_by_text("neutral", exact=True)
    )

    expect(neutral).to_contain_text("The neutral clip is locked.")
    expect(neutral.get_by_role("button", name="Regenerate")).to_have_count(0)
    expect(neutral.get_by_role("button", name="Remove")).to_have_count(0)


def test_a_retune_on_a_saved_voice_waits_for_accept(vw: Page, live_app):
    card = save_voice(vw)
    card.locator("summary").click()
    angry = saved_preset(card, "angry")
    angry.locator('input[type="range"]').nth(0).fill("1")
    angry.locator('input[type="range"]').nth(1).fill("0.25")

    angry.get_by_role("button", name="Hear these values").click()

    pending = card.locator(".pending")
    expect(pending).to_contain_text("New values for angry: exaggeration 1, cfg 0.25. Keep it?")
    pending.get_by_role("button", name="Accept").click()
    expect(card.locator(".pending")).to_have_count(0)
    angry = vw.request.get(f"{live_app.url}/voices").json()[0]["presets"]["angry"]
    assert (angry["exaggeration"], angry["cfg"]) == (1, 0.25)


def test_a_rejected_take_leaves_the_preset_as_it_was(vw: Page, live_app):
    card = save_voice(vw)
    card.locator("summary").click()
    angry = saved_preset(card, "angry")
    before = vw.request.get(f"{live_app.url}/voices").json()[0]["presets"]["angry"]

    angry.get_by_role("button", name="Regenerate").click()
    card.locator(".pending").get_by_role("button", name="Reject").click()

    expect(card.locator(".pending")).to_have_count(0)
    assert vw.request.get(f"{live_app.url}/voices").json()[0]["presets"]["angry"] == before


def test_adding_an_emotion_preset_to_a_saved_voice(vw: Page):
    card = save_voice(vw)
    card.locator("summary").click()
    form = card.locator("form[data-add-preset-for]")
    form.get_by_placeholder("angry-soft").fill("angry-soft")
    form.get_by_placeholder("Optional sample sentence").fill("Put that down, please.")

    form.get_by_role("button", name="Design it").click()

    expect(card.locator(".pending")).to_contain_text("New angry-soft clip. Keep it?")
    card.locator(".pending").get_by_role("button", name="Accept").click()
    expect(card.locator(".chip.emotion")).to_have_text(EMOTIONS + ["angry-soft"])


def test_removing_an_emotion_preset_asks_first(vw: Page):
    card = save_voice(vw)
    card.locator("summary").click()
    excited = saved_preset(card, "excited")
    dialog = vw.locator("#confirm-dialog")

    excited.get_by_role("button", name="Remove").click()
    expect(dialog).to_contain_text("Remove excited?")
    dialog.get_by_role("button", name="Cancel").click()
    expect(card.locator(".chip.emotion")).to_have_text(EMOTIONS)

    excited.get_by_role("button", name="Remove").click()
    dialog.get_by_role("button", name="Remove").click()
    expect(card.locator(".chip.emotion")).to_have_text(["neutral", "angry", "sad"])


def test_deleting_a_saved_voice_asks_then_removes_it(vw: Page):
    card = save_voice(vw, "QA Narrator")
    card.locator("summary").click()
    dialog = vw.locator("#confirm-dialog")

    card.get_by_role("button", name="Delete QA Narrator").click()
    expect(dialog).to_be_visible()
    expect(dialog.locator("#confirm-title")).to_have_text("Delete QA Narrator?")
    vw.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(vw.locator("#voices details.card")).to_have_count(1)

    card.get_by_role("button", name="Delete QA Narrator").click()
    dialog.get_by_role("button", name="Delete").click()

    expect(vw.locator("#voices details.card")).to_have_count(0)
    expect(vw.locator("#no-voices")).to_be_visible()
    expect(vw.locator("#badge-voices")).to_have_text("")


def test_discarding_a_draft_asks_first(vw: Page):
    design_voice(vw, "A voice to throw away.")
    drafts = vw.locator("#drafts")
    dialog = vw.locator("#confirm-dialog")

    drafts.get_by_role("button", name="Discard").click()
    expect(dialog.locator("#confirm-title")).to_have_text("Discard this Draft voice?")
    # Enter lands on Cancel, which has the focus: the draft stays.
    vw.keyboard.press("Enter")
    expect(dialog).to_be_hidden()
    expect(drafts).to_contain_text("A voice to throw away.")
    # So does a click outside the dialog.
    drafts.get_by_role("button", name="Discard").click()
    vw.mouse.click(5, 5)
    expect(dialog).to_be_hidden()
    expect(drafts).to_contain_text("A voice to throw away.")

    drafts.get_by_role("button", name="Discard").click()
    dialog.get_by_role("button", name="Discard").click()

    expect(vw.locator("#drafts-area")).to_be_hidden()
    expect(vw.locator("#review")).to_be_hidden()


def test_a_draft_survives_a_reload_and_can_be_resumed(vw: Page):
    design_voice(vw, "A voice worth keeping.")

    vw.reload()
    expect(vw.locator("#review")).to_be_hidden()
    vw.locator("#drafts").get_by_role("button", name="Resume").click()

    expect(vw.locator("#review textarea")).to_have_value("A voice worth keeping.")


def test_the_job_bar_names_each_design_step(vw: Page, live_app):
    held = Held(live_app.fakes, at_call=1)  # pause before the angry preset
    area(vw, "voices")
    vw.locator("#design-description").fill("A calm voice.")
    vw.get_by_role("button", name="Design", exact=True).click()

    expect(vw.locator("#job")).to_be_visible()
    expect(vw.locator("#job-message")).to_contain_text("angry")
    expect(vw.locator("#job-message")).to_contain_text("of 4)")
    expect(vw.get_by_role("button", name="Design", exact=True)).to_be_disabled()

    held.release.set()
    expect(vw.locator("#job")).to_be_hidden()
    expect(vw.get_by_role("button", name="Design", exact=True)).to_be_enabled()
    expect(vw.locator("#review")).to_be_visible()
