/** @odoo-module **/

import { router } from "@web/core/browser/router";
import { rpc } from "@web/core/network/rpc";
import { browser } from "@web/core/browser/browser";

/**
 * Report the current route to the server so the activity log knows which
 * screen each session is on.
 *
 * This used to be done by reassigning router.pushState/replaceState with a
 * copy of Odoo's own router internals. That copy carried its own module-level
 * `state`, so core's `state` was never updated again and `router.current`
 * returned the state captured at page load forever. Anything reading
 * router.current after a navigation got a stale answer -- Studio in
 * particular would load, push its URL, and then be re-rendered away by the
 * previous action.
 *
 * Core's implementation is now left alone and simply wrapped.
 */

const NOTIFY_DELAY = 1000;

const pushState = router.pushState.bind(router);
const replaceState = router.replaceState.bind(router);

let notifyTimeout = null;
let lastPayload = null;

function notify() {
    // Core debounces its own push, so read router.current only once the
    // history entry has actually been written.
    const state = router.current;
    if (!state || !Object.keys(state).length) {
        return;
    }
    const payload = JSON.stringify(state);
    if (payload === lastPayload) {
        return;
    }
    lastPayload = payload;
    // Fire and forget: session logging must never block or break navigation.
    rpc("/post/action_data", { data: state }).catch(() => {});
}

function scheduleNotify() {
    browser.clearTimeout(notifyTimeout);
    notifyTimeout = browser.setTimeout(notify, NOTIFY_DELAY);
}

router.pushState = function (state, options) {
    const result = pushState(state, options);
    scheduleNotify();
    return result;
};

router.replaceState = function (state, options) {
    const result = replaceState(state, options);
    scheduleNotify();
    return result;
};

// Back/forward navigation changes the route without going through pushState.
browser.addEventListener("popstate", scheduleNotify);
