from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:8000"
SCREENSHOT = Path(__file__).resolve().parents[1] / "demo_screenshot.png"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="networkidle")
            page.locator("#chat-input").fill(
                "I'm looking for a 1-bedroom apartment in Indianapolis for $1,450 per month."
            )
            page.locator("#chat-form").evaluate("form => form.requestSubmit()")
            page.locator("#chat-log .verdict-card").first.wait_for(state="visible")
            page.screenshot(path=str(SCREENSHOT), full_page=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
