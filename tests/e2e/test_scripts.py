"""Scripts in the browser: write a tagged Script, check it, fix what it's missing, generate it,
and play, save, and download the Output (spec stories 36-55)."""

import json
import wave

from playwright.sync_api import Page, expect

from e2e.helpers import add_sound, area, played, save_voice

TAGGED = "The storm had been building. [angry] Get inside! {thunder} [sad] Too late."


def write(page: Page, script: str):
    area(page, "scripts")
    page.locator("#script-text").fill(script)


def test_with_no_saved_voice_the_scripts_area_says_to_design_one(vw: Page):
    area(vw, "scripts")

    expect(vw.locator("#script-no-voices")).to_be_visible()
    expect(vw.locator("#script-voice")).to_be_hidden()
    expect(vw.locator("#no-outputs")).to_be_visible()
    expect(vw.locator("#no-saved")).to_be_visible()

    vw.locator("#script-text").fill("Hello.")
    vw.get_by_role("button", name="Check").click()
    expect(vw.locator("#script-error")).to_have_text("Save a Voice first, then pick it here.")


def test_tags_are_colored_as_typed_and_a_bad_one_is_marked(vw: Page):
    write(vw, "Calm. [angry] Loud! {thunder} (laugh) [bad tag]")

    highlight = vw.locator("#script-highlight")
    expect(highlight.locator(".tok-emotion").first).to_have_text("[angry]")
    expect(highlight.locator(".tok-sound")).to_have_text("{thunder}")
    expect(highlight.locator(".tok-effect")).to_have_text("(laugh)")
    expect(highlight.locator(".tok-unknown")).to_have_text("[bad tag]")
    expect(vw.locator("#script-count")).to_have_text("47 / 20,000 characters")


def test_the_palette_inserts_the_voice_emotions_and_library_sounds(vw: Page):
    save_voice(vw, "Narrator")
    add_sound(vw, "thunder", "thunder")
    write(vw, "Hello")

    vw.locator("#script-palette").get_by_role("button", name="[angry]").click()
    vw.locator("#script-palette").get_by_role("button", name="{thunder}").click()

    expect(vw.locator("#script-text")).to_have_value("Hello [angry] {thunder}")


def test_the_check_lists_every_missing_emotion_and_sound_and_bad_tag(vw: Page):
    save_voice(vw, "QA Narrator")
    write(vw, "Calm. [furious] Stop! {thunder} (gasp)\n[sad never closed")

    vw.get_by_role("button", name="Check").click()

    result = vw.locator("#script-result")
    expect(result).to_contain_text("Fix these before generating:")
    problems = result.locator("ul.problems li")
    expect(problems).to_have_count(3)
    expect(problems.nth(0)).to_contain_text("[furious] QA Narrator has no furious preset.")
    expect(problems.nth(1)).to_contain_text("{thunder} isn't in your Sound library.")
    expect(problems.nth(2)).to_contain_text("Line 2, column 1")
    expect(result.locator("ul.warnings li")).to_contain_text("(gasp) is skipped")


def test_a_problem_position_selects_it_in_the_script(vw: Page):
    save_voice(vw)
    write(vw, "Fine.\n[sad never closed")
    vw.get_by_role("button", name="Check").click()

    vw.get_by_role("button", name="Line 2, column 1").click()

    selected = vw.locator("#script-text").evaluate(
        "(t) => [t.selectionStart, t.selectionEnd, document.activeElement === t]"
    )
    assert selected == [6, 7, True]


def test_find_it_on_freesound_searches_for_the_missing_sound_then_the_check_reruns(vw: Page):
    save_voice(vw)
    write(vw, TAGGED)
    vw.get_by_role("button", name="Check").click()

    vw.get_by_role("button", name="Find it on Freesound").click()

    expect(vw.locator("#area-sounds")).to_be_visible()
    expect(vw.locator("#sound-query")).to_have_value("thunder")
    result = vw.locator("#sound-results .card").first
    expect(result.get_by_role("textbox")).to_have_value("thunder")
    result.get_by_role("button", name="Add").click()
    expect(result).to_contain_text("Added as {thunder}.")

    area(vw, "scripts")
    expect(vw.locator("#script-result")).to_contain_text("Ready to generate: 4 Segments.")


def test_add_emotion_opens_the_voice_with_the_name_filled_in(vw: Page):
    save_voice(vw, "QA Narrator")
    write(vw, "[furious] Stop!")
    vw.get_by_role("button", name="Check").click()

    vw.get_by_role("button", name="Add furious to QA Narrator").click()

    expect(vw.locator("#area-voices")).to_be_visible()
    form = vw.locator("form[data-add-preset-for]")
    expect(form.get_by_placeholder("angry-soft")).to_have_value("furious")
    expect(form.get_by_placeholder("angry-soft")).to_be_focused()


def test_generating_plays_the_output_then_saving_keeps_it_with_its_record(vw: Page, live_app):
    save_voice(vw, "QA Narrator")
    add_sound(vw, "thunder", "thunder")
    write(vw, TAGGED)

    vw.get_by_role("button", name="Generate").click()

    expect(vw.locator("#script-result")).to_contain_text("It's at the top of Recent Outputs.")
    output = vw.locator("#outputs .card").first
    expect(output).to_contain_text("QA Narrator")
    expect(output.locator(".excerpt")).to_have_text(TAGGED)
    expect(vw.locator("#badge-scripts")).to_have_text("1")
    assert played(vw, output.locator("audio"))
    spoken = [c.inputs["text"] for c in live_app.fakes.calls if c.model == "speech"]
    assert spoken[-3:] == ["The storm had been building.", "Get inside!", "Too late."]

    output.get_by_role("button", name="Save").click()

    expect(output.locator(".saved-tag")).to_have_text("Saved")
    saved = vw.locator("#saved .card").first
    expect(saved).to_contain_text(
        'Sounds: {thunder} "Distant Thunder" by artist202 (Attribution 4.0)'
    )
    expect(vw.locator("#no-saved")).to_be_hidden()
    record = vw.request.get(
        live_app.url + saved.get_by_role("link", name="Record (JSON)").get_attribute("href")
    ).json()
    assert record["script"] == TAGGED
    assert record["voice"]["name"] == "QA Narrator"
    assert json.dumps(record).count("Attribution 4.0") >= 1


def test_an_output_downloads_as_a_standard_wav(vw: Page, tmp_path):
    save_voice(vw, "QA Narrator")
    write(vw, "Just one line.")
    vw.get_by_role("button", name="Generate").click()
    output = vw.locator("#outputs .card").first

    with vw.expect_download() as info:
        output.get_by_role("link", name="Download WAV").click()

    download = info.value
    assert download.suggested_filename.startswith("qa-narrator-")
    assert download.suggested_filename.endswith(".wav")
    path = tmp_path / "output.wav"
    download.save_as(path)
    with wave.open(str(path)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth()) == (1, 2)


def test_command_enter_generates(vw: Page):
    save_voice(vw)
    write(vw, "Typed and sent from the keyboard.")

    vw.locator("#script-text").press("Control+Enter")

    expect(vw.locator("#outputs .card")).to_have_count(1)


def test_a_script_with_problems_is_not_generated(vw: Page, live_app):
    save_voice(vw)
    write(vw, "[furious] Stop!")
    calls_before = len(live_app.fakes.calls)

    vw.get_by_role("button", name="Generate").click()

    expect(vw.locator("#script-result")).to_contain_text("Fix these before generating:")
    expect(vw.locator("#outputs .card")).to_have_count(0)
    assert len(live_app.fakes.calls) == calls_before


def test_the_script_and_voice_survive_a_reload(vw: Page):
    save_voice(vw, "First")
    save_voice(vw, "Second", "A second, brighter voice.")
    write(vw, "Keep this text.")
    vw.locator("#script-voice").select_option(label="Second")

    vw.reload()
    area(vw, "scripts")

    expect(vw.locator("#script-text")).to_have_value("Keep this text.")
    expect(vw.locator("#script-voice option:checked")).to_have_text("Second")


def test_the_cache_size_keeps_only_that_many_recent_outputs(vw: Page, live_app):
    save_voice(vw)
    write(vw, "Line.")
    for count in range(1, 7):
        vw.get_by_role("button", name="Generate").click()
        expect(vw.locator("#outputs .card")).to_have_count(min(count, 5))
    expect(vw.locator("#cache-size")).to_have_value("5")

    vw.locator("#cache-size").select_option("6")
    vw.get_by_role("button", name="Generate").click()

    expect(vw.locator("#outputs .card")).to_have_count(6)
    assert "output_cache_size = 6" in live_app.config_path.read_text()
