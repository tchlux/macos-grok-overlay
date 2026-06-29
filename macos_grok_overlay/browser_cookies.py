# Import login cookies from Chrome into the overlay WKWebView.
#
# Chrome and the overlay use separate cookie stores. Reading Chrome cookies and
# injecting them is required to sync a browser login into the overlay.

import browser_cookie3
from Foundation import (
    NSDate,
    NSHTTPCookie,
    NSHTTPCookieDomain,
    NSHTTPCookieExpires,
    NSHTTPCookieName,
    NSHTTPCookiePath,
    NSHTTPCookieSecure,
    NSHTTPCookieValue,
)

SYNC_DOMAIN_MARKERS = (
    "grok.com",
    "x.ai",
    "accounts.x.ai",
    "x.com",
    "twitter.com",
)


def _domain_matches(domain):
    host = domain.lstrip(".").lower()
    return any(marker == host or host.endswith("." + marker) for marker in SYNC_DOMAIN_MARKERS)


def _collect_cookies():
    cookies = []
    try:
        jar = browser_cookie3.chrome()
    except Exception as error:
        print(f"Could not read Chrome cookies: {error}", flush=True)
        return cookies
    for cookie in jar:
        if _domain_matches(cookie.domain):
            cookies.append(cookie)
    return cookies


def _ns_cookie_from_jar_cookie(cookie):
    properties = {
        NSHTTPCookieName: cookie.name,
        NSHTTPCookieValue: cookie.value,
        NSHTTPCookieDomain: cookie.domain,
        NSHTTPCookiePath: cookie.path or "/",
        NSHTTPCookieSecure: bool(cookie.secure),
    }
    if cookie.expires and cookie.expires > 0:
        properties[NSHTTPCookieExpires] = NSDate.dateWithTimeIntervalSince1970_(
            float(cookie.expires)
        )
    return NSHTTPCookie.cookieWithProperties_(properties)


def sync_browser_cookies_to_webview(webview, completion_handler=None):
    """Copy Grok-related cookies from Chrome into the overlay webview."""
    cookies = _collect_cookies()
    if not cookies:
        print("No Grok session cookies found in Chrome.", flush=True)
        if completion_handler is not None:
            completion_handler(0)
        return

    ns_cookies = []
    for cookie in cookies:
        ns_cookie = _ns_cookie_from_jar_cookie(cookie)
        if ns_cookie is not None:
            ns_cookies.append(ns_cookie)

    store = webview.configuration().websiteDataStore().httpCookieStore()

    def set_at_index(index, imported_count):
        if index >= len(ns_cookies):
            print(f"Imported {imported_count} browser cookies into overlay.", flush=True)
            if completion_handler is not None:
                completion_handler(imported_count)
            return

        def after_set():
            set_at_index(index + 1, imported_count + 1)

        store.setCookie_completionHandler_(ns_cookies[index], after_set)

    set_at_index(0, 0)