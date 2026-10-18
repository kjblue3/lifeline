# LifeLine Samsung PWA

## Install

Current public app URL:

https://still-burlington-neck-eur.trycloudflare.com/assets/index.html

1. Remove the old LifeLine Home-screen shortcut if it opens the wrong hostname
   or still has the Chrome shortcut badge. This does not require clearing all
   browser data.
2. Open the exact app URL above in **regular Chrome**, not Incognito or an
   embedded WhatsApp/CoShell browser. Installation is not available in Incognito.
3. Stay online until the app finishes loading. Open a screen or tap a navigation
   item, then open Chrome's three-dot menu.
4. Choose **Install app**, or **Add to Home screen > Install**, depending on the
   Chrome version. Confirm the installation named **LifeLine**. If Chrome only
   offers **Create shortcut**, do not treat that as a completed app installation.
5. Launch LifeLine from the new launcher/app-drawer icon. It should open in its
   own window without Chrome's address bar. Opening its URL in a normal Chrome
   tab will still show the address bar; standalone mode applies to the installed
   app launch.
6. After the first online load completes, close the app, turn off Wi-Fi/mobile
   data, and reopen it. The app interface and bundled preparedness checklist
   should load. Chat must not claim that AI is running on the Samsung.

Android handles installation/WebAPK provisioning. A normal online Chrome
session and a supported, updated device/browser are required for the actual
device installation. If the menu still offers only a shortcut, update Chrome,
reload the current URL, close old LifeLine tabs, and try again. As a last resort,
clear data for **this hostname only**; doing so removes its cached interface and
any saved checklist progress. Reopen online before retrying installation.

## Configuration

- App name and short name: `LifeLine`.
- Stable app ID within this origin: `/assets/`.
- Launch URL: `/assets/index.html`.
- Manifest and service-worker scope: `/assets/`.
- Display: `standalone`.
- Full-color PNG launcher icons: 192x192 and 512x512, rendered from the existing
  LifeLine vector artwork. A maskable 512x512 entry gives Android safe cropping.
- HTTPS is provided by the existing Cloudflare tunnel to the restricted
  frontend preview on port 8010. Neither server nor tunnel needs a restart for
  these assets; the preview serves the current frontend files live.

The source service worker explicitly caches public app-shell files only. The
public preview's existing service worker uses network-first frontend caching so
saved edits appear online while cached interface files remain usable offline.
Both use the same `/assets/` scope. Cache versions are updated when assets change.

No API responses, questions, generated answers, in-memory profiles, recordings,
or attachments are written to the service-worker cache. The pre-existing
preparedness Save feature uses a separate localStorage key for item checkmarks;
this change does not add profile persistence. New reference-library content is
owned by the frontend team and is separate from the backend medical database.

An offline interface is not offline AI, a clinical readiness claim, or an
emergency communication connection. External source links and actual phone
calls require their respective communication services. Cached data can be
cleared by the user or evicted by Android, so offline availability depends on
the device retaining the installed app-shell cache.

The free Quick Tunnel hostname is temporary. The installed app remains tied to
this origin: a new tunnel hostname is a different app origin, not an automatic
update of the old install. The existing hostname has been preserved for this task.

## Verification

```sh
.venv/bin/python -B pwa_check.py https://still-burlington-neck-eur.trycloudflare.com/assets/index.html
```

The browser check uses isolated desktop and mobile Chromium contexts, verifies
the actual downloaded PNG signatures/dimensions, checks the parsed manifest and
Chromium installability errors, and waits for service-worker control. It saves
only a clearly fictional profile, audits caches for frontend-only URLs and no
private marker, then opens a new page with network access disabled. It verifies
interface navigation, checklist availability, cleared in-memory profile,
emergency dialog access, and online recovery.

These checks do not install an Android WebAPK or physically test a Samsung.
Launcher icon appearance and absence of the address bar on installed launch
must be confirmed on the Galaxy S25 Ultra using the steps above.
