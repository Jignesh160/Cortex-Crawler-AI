"""Render-type detection: SPA shells trigger the browser fallback; SSR/static don't."""
from cortexcrawler.engine.extract import is_spa_shell

SPA_SHELL = """<!doctype html><html><head><title>App</title></head>
<body><div id="__nuxt"></div><script src="/_nuxt/app.js"></script></body></html>"""

SPA_SHELL_WITH_NAV = """<!doctype html><html><body>
<nav>Home Models Contact About Service Offers Finance Careers News Locations</nav>
<div id="root"></div><script src="/static/bundle.js"></script></body></html>"""

SSR_PAGE = """<!doctype html><html><body><div id="__nuxt"><main>
<h1>Chery Tiggo 8</h1>
<p>%s</p></main></div></body></html>""" % ("The Tiggo 8 is a premium seven seat SUV. " * 60)

STATIC_PAGE = """<!doctype html><html><body><article>
<h1>About Us</h1><p>%s</p></article></body></html>""" % ("We are a car dealership. " * 60)


def test_spa_shell_detected():
    assert is_spa_shell(SPA_SHELL) is True


def test_spa_shell_with_some_nav_still_detected():
    assert is_spa_shell(SPA_SHELL_WITH_NAV) is True


def test_ssr_page_not_a_shell():
    # Has a Nuxt mount node but plenty of server-rendered text -> no browser needed.
    assert is_spa_shell(SSR_PAGE) is False


def test_static_page_not_a_shell():
    assert is_spa_shell(STATIC_PAGE) is False
