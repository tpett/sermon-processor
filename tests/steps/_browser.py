import threading
from contextlib import contextmanager

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from steps import _web


@contextmanager
def serves(store):
    server = make_server("127.0.0.1", 0, _web.opens_app(store), threaded=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        worker.join()


@contextmanager
def opens_page(store):
    with serves(store) as base, sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            page = browser.new_page(base_url=base, viewport={"width": 1400, "height": 1000})
            yield page
        finally:
            browser.close()


def clicks_at_seconds(page, selector, seconds):
    """A real click on a pane at the pixel its own window maps to `seconds`."""
    pane = page.locator(selector)
    start = float(pane.get_attribute("data-window-start-seconds"))
    across = float(pane.get_attribute("data-window-seconds"))
    box = pane.bounding_box()
    page.mouse.click(
        box["x"] + box["width"] * (seconds - start) / across,
        box["y"] + box["height"] / 2,
    )
