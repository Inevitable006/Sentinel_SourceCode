# Connect Gmail and Google Calendar

Sentinel uses Google's Desktop OAuth flow with PKCE. Your Google password is entered only in Google's browser sign-in page, never in Sentinel or chat.

1. In your Google Cloud project, enable **Gmail API** and **Google Calendar API**.
2. Configure the OAuth consent screen. If the project is in testing, add your own account as a test user. Google may limit the lifetime of testing grants.
3. Create an OAuth client with application type **Desktop app**, then download its JSON credentials. Keep this file outside the repository.
4. Open Sentinel → Settings → **Gmail and Google Calendar**. Import the JSON and choose **Save credentials**. Enter your Sentinel PIN if requested.
5. Choose **Connect Google**, copy the link into your normal browser, and select the read-only permissions you want. The sign-in link expires in five minutes.
6. When the browser says to return to Sentinel, choose **Finish connection**. Press **Refresh Gmail** or **Refresh Calendar** to request data.

The Gmail view shows at most ten inbox previews. Calendar shows at most twenty-five primary-calendar events in the next seven days. A message says when more results exist. These views do not automatically refresh, send mail, modify events or cache message/event contents in the database. Existing Workspace drafts stay local.

OAuth credentials and tokens are stored in the encrypted vault; they are not returned to the UI after saving. Locking cancels pending consent and invalidates in-flight results. Offline mode blocks backend Google requests. Browser sign-in is a separate, explicit browser action.

**Disconnect and remove credentials** removes local tokens and client configuration. To revoke Google's grant too, remove the application from your Google Account's third-party access controls. Re-import your desktop client JSON to connect again.

If a permission is omitted, its Refresh button stays unavailable. Reconnect to grant it. For HTTP errors, check enabled APIs, consent/test-user configuration and network access. Expired or revoked credentials require reconnection. Do not paste authorization codes, tokens or client secrets into chat.

Implementation verified with isolated tests and mocked Google responses. Live account consent has not been performed by the development agent.

Sources: [Google Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [Gmail message listing](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list), [Calendar event listing](https://developers.google.com/workspace/calendar/api/v3/reference/events/list).
