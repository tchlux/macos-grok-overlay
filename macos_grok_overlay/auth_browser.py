# Authentication must run in the user's browser, not embedded WKWebView.
#
# WKWebView cannot complete passkey / security-key ceremonies for third-party providers.
# Real browsers support the 1Password extension and full WebAuthn.

import os
import subprocess
import time

import objc
from AppKit import (
    NSAlert,
    NSAlertStyleInformational,
    NSApp,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSMakeRect,
    NSRunningApplication,
    NSTextField,
    NSWorkspace,
    NSWorkspaceOpenConfiguration,
)
from Foundation import NSObject, NSURL
from WebKit import (
    WKNavigationActionPolicyAllow,
    WKNavigationActionPolicyCancel,
    WKNavigationTypeFormResubmitted,
    WKNavigationTypeFormSubmitted,
    WKNavigationTypeLinkActivated,
)

from .constants import WEBSITE

BROWSER_BUNDLE_IDS = frozenset({
    "com.google.Chrome",
    "org.mozilla.firefox",
    "company.thebrowser.Browser",
    "com.brave.Browser",
    "com.microsoft.edgemac",
    "com.operasoftware.Opera",
    "com.vivaldi.Vivaldi",
})

AUTH_HOSTS = frozenset({
    "accounts.google.com",
    "myaccount.google.com",
    "accounts.x.ai",
    "x.com",
    "twitter.com",
    "appleid.apple.com",
    "login.microsoftonline.com",
})

AUTH_HOST_SUFFIXES = (
    ".google.com",
    ".x.com",
    ".twitter.com",
    ".x.ai",
)

AUTH_PATH_MARKERS = (
    "/oauth",
    "/i/oauth2",
    "/signin",
    "/sign-in",
    "/login",
    "/log-in",
    "/auth",
    "/account",
    "/passkey",
    "/webauthn",
    "/security-key",
    "/securitykey",
    "/2fa",
    "/mfa",
    "/verify",
)

AUTH_CALLBACK_HOSTS = frozenset({
    "grok.com",
    "x.ai",
    "accounts.x.ai",
})

USER_INITIATED_NAVIGATION_TYPES = frozenset({
    WKNavigationTypeLinkActivated,
    WKNavigationTypeFormSubmitted,
    WKNavigationTypeFormResubmitted,
})

AUTH_CLICK_INTERCEPTOR_SCRIPT = """
(function () {
    function post() {
        try {
            window.webkit.messageHandlers.authRedirectHandler.postMessage("browser");
        } catch (e) {}
    }
    function shouldRedirect(el) {
        if (!el) return false;
        const href = String(el.href || el.getAttribute("href") || "").toLowerCase();
        const text = String(el.textContent || el.innerText || "").toLowerCase();
        const label = String(el.getAttribute("aria-label") || "").toLowerCase();
        const combined = text + " " + label + " " + href;
        const hostHints = [
            "accounts.google", "google.com/o/oauth", "appleid.apple",
            "x.com/i/oauth", "twitter.com/i/oauth", "accounts.x.ai", "x.ai/auth"
        ];
        if (hostHints.some((hint) => href.includes(hint))) return true;
        const textHints = [
            "sign in with google", "continue with google", "log in with google",
            "sign in with x", "continue with x", "log in with x",
            "sign in with apple", "continue with apple",
            "sign in", "log in", "login", "passkey", "security key",
            "continue with", "use password", "try another way"
        ];
        return textHints.some((hint) => combined.includes(hint));
    }
    document.addEventListener("click", function (event) {
        const el = event.target.closest("a, button, [role='button'], input[type='submit']");
        if (!shouldRedirect(el)) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        post();
    }, true);
})();
"""


def _host_from_url(url_string):
    if not url_string:
        return ""
    marker = "://"
    start = url_string.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    end = url_string.find("/", start)
    host = url_string[start:end] if end != -1 else url_string[start:]
    port = host.find(":")
    return host[:port].lower() if port != -1 else host.lower()


def _path_from_url(url_string):
    if not url_string:
        return ""
    marker = "://"
    start = url_string.find(marker)
    if start == -1:
        return url_string.lower()
    start = url_string.find("/", start + len(marker))
    if start == -1:
        return ""
    query = url_string.find("?", start)
    return url_string[start:query].lower() if query != -1 else url_string[start:].lower()


def is_external_auth_url(url_string):
    host = _host_from_url(url_string)
    if not host:
        return False
    if host in AUTH_HOSTS:
        return True
    if any(host.endswith(suffix) for suffix in AUTH_HOST_SUFFIXES):
        path = _path_from_url(url_string)
        return any(marker in path for marker in AUTH_PATH_MARKERS)
    return False


def is_overlay_login_redirect(url_string):
    if is_external_auth_url(url_string):
        return True
    host = _host_from_url(url_string)
    if host in AUTH_CALLBACK_HOSTS:
        path = _path_from_url(url_string)
        return any(marker in path for marker in AUTH_PATH_MARKERS)
    return False


def is_login_page_url(url_string):
    return is_overlay_login_redirect(url_string)


def sign_in_entry_url():
    return NSURL.URLWithString_(WEBSITE)


class AuthBrowserManager:
    """Plain Python helper (not NSObject) to avoid PyObjC selector issues."""

    def __init__(self, app_delegate):
        self.app_delegate = app_delegate
        self._auth_session_active = False
        self._main_webview_auth_active = False
        self._pending_browser_auth = False
        self._last_browser_open = 0.0
        self._saved_activation_policy = NSApplicationActivationPolicyAccessory

    def _recently_opened_browser(self):
        return (time.time() - self._last_browser_open) < 2.0

    def _sync_activation_policy(self):
        needs_auth = self._main_webview_auth_active or self._pending_browser_auth
        if needs_auth:
            if not self._auth_session_active:
                self._saved_activation_policy = NSApp.activationPolicy()
                NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
                self._auth_session_active = True
            NSApp.activateIgnoringOtherApps_(True)
            return
        if self._auth_session_active:
            NSApp.setActivationPolicy_(self._saved_activation_policy)
            self._auth_session_active = False

    def set_main_webview_needs_auth(self, needs_auth):
        self._main_webview_auth_active = bool(needs_auth)
        self._sync_activation_policy()

    def consume_pending_browser_auth_reload(self):
        if self._pending_browser_auth:
            self._pending_browser_auth = False
            return True
        return False

    def open_sign_in_in_browser(self, url=None, show_instructions=True):
        if self._recently_opened_browser():
            return
        if url is None:
            url = sign_in_entry_url()
        self._last_browser_open = time.time()
        self._pending_browser_auth = True
        self._main_webview_auth_active = True
        self._sync_activation_policy()
        browser_name, _browser_bundle_id = self._open_in_preferred_browser(url)
        if show_instructions:
            self._show_browser_instructions(browser_name)

    def handle_user_auth_request(self, restore_overlay=True):
        self.open_sign_in_in_browser(sign_in_entry_url(), show_instructions=True)
        if restore_overlay:
            self.app_delegate.loadOverlayHomePage_(None)

    def _running_browser_for_bundle_id(self, bundle_id):
        apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
        return apps[0] if apps else None

    def _default_browser_app_url(self, url):
        return NSWorkspace.sharedWorkspace().URLForApplicationToOpenURL_(url)

    def _open_with_application(self, app_url, url):
        config = NSWorkspaceOpenConfiguration.configuration()
        config.setActivates_(True)
        NSWorkspace.sharedWorkspace().openURLs_withApplicationAtURL_configuration_completionHandler_(
            [url],
            app_url,
            config,
            lambda app, err: None,
        )

    def _open_in_preferred_browser(self, url):
        workspace = NSWorkspace.sharedWorkspace()

        front = workspace.frontmostApplication()
        if front is not None:
            bundle_id = str(front.bundleIdentifier())
            if bundle_id in BROWSER_BUNDLE_IDS:
                app_url = front.bundleURL()
                if app_url is not None:
                    self._open_with_application(app_url, url)
                    return str(front.localizedName()), bundle_id

        default_app_url = self._default_browser_app_url(url)
        default_bundle_id = None
        if default_app_url is not None:
            default_path = os.path.realpath(str(default_app_url.path()))
            for bundle_id in BROWSER_BUNDLE_IDS:
                running = self._running_browser_for_bundle_id(bundle_id)
                if running is None:
                    continue
                app_url = running.bundleURL()
                if app_url is None:
                    continue
                if os.path.realpath(str(app_url.path())) == default_path:
                    self._open_with_application(app_url, url)
                    return str(running.localizedName()), bundle_id
            default_name = workspace.localizedNameForApplicationAtURL_(default_app_url)
            for bundle_id in BROWSER_BUNDLE_IDS:
                app_path = workspace.absolutePathForAppBundleWithIdentifier_(bundle_id)
                if app_path and os.path.realpath(app_path) == default_path:
                    default_bundle_id = bundle_id
                    break

        running_browsers = []
        for bundle_id in BROWSER_BUNDLE_IDS:
            running = self._running_browser_for_bundle_id(bundle_id)
            if running is not None:
                running_browsers.append((running, bundle_id))
        if len(running_browsers) == 1:
            app, bundle_id = running_browsers[0]
            app_url = app.bundleURL()
            if app_url is not None:
                self._open_with_application(app_url, url)
                return str(app.localizedName()), bundle_id

        if workspace.openURL_(url):
            name = "your default browser"
            if default_app_url is not None:
                name = workspace.localizedNameForApplicationAtURL_(default_app_url) or name
            return name, default_bundle_id

        subprocess.run(["open", str(url.absoluteString())], check=False)
        return "your default browser", default_bundle_id

    def _show_browser_instructions(self, browser_name):
        alert = NSAlert.alloc().init()
        alert.setAlertStyle_(NSAlertStyleInformational)
        alert.setMessageText_(f"Continue sign-in in {browser_name}")
        alert.setInformativeText_(
            f"Sign-in has been opened in {browser_name}.\n\n"
            "Use the 1Password extension there — it does not work inside this overlay.\n\n"
            "When grok.com shows you as logged in, return to this app. Your login "
            "will be copied from your browser into the overlay automatically.\n\n"
            "You can also use the menu item \"Sync Login from Browser\" at any time."
        )
        alert.runModal()


class WebNavigationDelegate(NSObject):
    def initWithAppDelegate_(self, app_delegate):
        self = objc.super(WebNavigationDelegate, self).init()
        if self is None:
            return None
        self.app_delegate = app_delegate
        return self

    @objc.python_method
    def _is_user_initiated(self, navigation_action):
        return navigation_action.navigationType() in USER_INITIATED_NAVIGATION_TYPES

    @objc.python_method
    def _navigation_policy_for_action(self, webview, navigation_action):
        request = navigation_action.request()
        url_string = str(request.URL().absoluteString())

        if not is_external_auth_url(url_string):
            return WKNavigationActionPolicyAllow

        if self._is_user_initiated(navigation_action):
            self.app_delegate.auth_browser.handle_user_auth_request(restore_overlay=True)
            return WKNavigationActionPolicyCancel

        self.app_delegate.loadOverlayHomePage_(None)
        return WKNavigationActionPolicyCancel

    def webView_decidePolicyForNavigationAction_decisionHandler_(
        self, webview, navigation_action, decision_handler
    ):
        decision_handler(self._navigation_policy_for_action(webview, navigation_action))

    def webView_decidePolicyForNavigationAction_preferences_decisionHandler_(
        self, webview, navigation_action, preferences, decision_handler
    ):
        decision_handler(
            self._navigation_policy_for_action(webview, navigation_action),
            preferences,
        )

    def webView_didFinishNavigation_(self, webview, navigation):
        if webview == self.app_delegate.webview:
            self.app_delegate.updateAuthSessionForMainWebView()


class WebUIDelegate(NSObject):
    def initWithAppDelegate_(self, app_delegate):
        self = objc.super(WebUIDelegate, self).init()
        if self is None:
            return None
        self.app_delegate = app_delegate
        return self

    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
        self, webview, configuration, navigation_action, window_features
    ):
        if not navigation_action.targetFrame():
            self.app_delegate.auth_browser.handle_user_auth_request(restore_overlay=True)
        return None

    def webViewDidClose_(self, webview):
        return

    def webView_runJavaScriptAlertPanelWithMessage_initiatedByFrame_completionHandler_(
        self, webview, message, frame, completion_handler
    ):
        alert = NSAlert.alloc().init()
        alert.setAlertStyle_(NSAlertStyleInformational)
        alert.setMessageText_(str(message))
        alert.runModal()
        completion_handler()

    def webView_runJavaScriptConfirmPanelWithMessage_initiatedByFrame_completionHandler_(
        self, webview, message, frame, completion_handler
    ):
        alert = NSAlert.alloc().init()
        alert.setAlertStyle_(NSAlertStyleInformational)
        alert.setMessageText_(str(message))
        response = alert.runModal()
        completion_handler(response == 1000)

    def webView_runJavaScriptTextInputPanelWithPrompt_defaultText_initiatedByFrame_completionHandler_(
        self, webview, prompt, default_text, frame, completion_handler
    ):
        alert = NSAlert.alloc().init()
        alert.setAlertStyle_(NSAlertStyleInformational)
        alert.setMessageText_(str(prompt))
        input_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 240, 24))
        input_field.setStringValue_(str(default_text) if default_text else "")
        alert.setAccessoryView_(input_field)
        response = alert.runModal()
        if response == 1000:
            completion_handler(input_field.stringValue())
        else:
            completion_handler(None)