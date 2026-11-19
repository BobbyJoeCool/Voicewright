"""Steps the E2E tests share: open an area, design or save a Voice, add a sound, play a clip."""

import threading

from fakes import FakeEngines
from playwright.sync_api import Page, expect


class Held:
    """Pause the fake engines before a given call, so a test can see a job while it runs."""

    def __init__(self, fakes: FakeEngines, at_call: int = 0):
        self.release = threading.Event()
        self.reached = threading.Event()
        self.at_call = at_call
        fakes.before_call = self._wait

    def _wait(self, number: int) -> None:
        if number == self.at_call:
            self.reached.set()
            assert self.release.wait(timeout=30), "the test never released the held job"


def area(page: Page, name: str):
    """Open an area from the sidebar and return its section."""
    page.locator(f'.nav-item[data-area="{name}"]').click()
    section = page.locator(f"#area-{name}")
    expect(section).to_be_visible()
    return section


def played(page: Page, audio) -> bool:
    """Play `audio` and report whether the browser actually played some of it."""
    return audio.evaluate(
        """async (a) => {
            a.muted = true;
            a.currentTime = 0;
            await a.play();
            await new Promise((done) => setTimeout(done, 150));
            const ok = a.currentTime > 0 || a.ended;
            a.pause();
            return ok;
        }"""
    )


def design_voice(page: Page, description: str = "A gravelly older man, slow and calm."):
    """Design a Draft voice from the Voices area and wait for its review to open."""
    area(page, "voices")
    page.locator("#design-description").fill(description)
    page.get_by_role("button", name="Design", exact=True).click()
    review = page.locator("#review")
    expect(review.get_by_role("heading", name="Review the Draft voice")).to_be_visible()
    return review


def save_voice(page: Page, name: str = "Old Narrator", description: str | None = None):
    """Design a Draft voice and accept it under `name`; returns its saved card."""
    review = design_voice(page, description or "A gravelly older man, slow and calm.")
    review.get_by_placeholder("Old Narrator").fill(name)
    review.get_by_role("button", name="Accept").click()
    card = page.locator("#voices details.card").filter(has_text=name)
    expect(card).to_be_visible()
    return card


def search(page: Page, query: str):
    """Search the fake Freesound from the Sounds area; returns the result cards once they show."""
    area(page, "sounds")
    page.locator("#sound-query").fill(query)
    page.get_by_role("button", name="Search").click()
    # Wait for this search's answer, so no step acts on the last search's cards.
    expect(page.locator("#sound-search-status")).to_contain_text(f'"{query}"')
    return page.locator("#sound-results .card")


def add_sound(page: Page, query: str, name: str):
    """Search the fake Freesound for `query` and add the first result as {name}."""
    area(page, "sounds")
    result = search(page, query).first
    result.get_by_role("textbox").fill(name)
    result.get_by_role("button", name="Add").click()
    expect(result).to_contain_text(f"Added as {{{name}}}.")
