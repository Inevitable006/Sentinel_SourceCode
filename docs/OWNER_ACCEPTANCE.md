# Sentinel Owner Acceptance Guide

This guide provides a comprehensive, non-destructive acceptance protocol for the owner to verify Sentinel on Windows. It separates safe verification on your active machine from procedures requiring an isolated test profile.

---

## 1. Verification Guidelines & Safety Boundaries

> [!IMPORTANT]
> **Active Profile Safety**: The tests in Section 2 are non-destructive and designed to run safely on your daily machine.
> **Restore Safety**: Testing a backup restore **must only** be performed in a separate test profile or test machine (Section 3). Never restore a test backup over your active profile.

### Verification Status Classification
- **Automated Evidence**: Verified by automated test suites (`pytest`, `node --test frontend/tests/settings-*.test.mjs`, `tools/tests/readiness.test.mjs`). See dated run logs in `docs/runs/`.
- **Owner Manual Verification**: Interactive checks requiring human input and visual inspection on Windows.
- **Unsupported / External**: Hardware or service dependencies that cannot be validated offline or are currently not implemented.

---

## 2. Safe Current-Machine Acceptance Protocol

Follow these non-destructive steps in order:

### Check 1: Setup, Lock, and Exact PIN Unlock
- **Automated baseline**: Vault keywrap, Argon2id key derivation, and lock generation tracking pass in backend tests.
- **Manual steps**:
  1. If running for the first time, set an Owner PIN (at least 8 characters, or 10+ digits). Write down or store the displayed **Recovery Key** (hyphenated base32 string, e.g. `ABCD-EFGH-...`) exactly as shown.
  2. In the lower-left sidebar, click **Lock Sentinel**.
  3. Verify that the UI displays the Lock screen, prompting for your PIN.
  4. Type your exact PIN (including any spaces if chosen) and click **Unlock**.
  5. Verify that the application unlocks and returns to Console.
- **PIN Freshness Rule**: Successful PIN verification authorizes sensitive actions for **five minutes from verification** (not inactivity). After five minutes from verification or upon locking, PIN re-verification is required. Subsequent sensitive actions within this 5-minute window reuse authorization without prompting again.

### Check 2: Typed Local Chat & Model Loading
- **Automated baseline**: Automated test suites pass (see dated run logs in `docs/runs/`); calculation tools run in isolated worker processes.
- **Manual steps**:
  1. Navigate to **Console**.
  2. Verify that **Core AI Processor** badge displays `Connected`.
  3. If the model is not loaded, click **Load Local Model** and observe the status transition from `Loading...` to `Model Ready`.
  4. Enter a test prompt (e.g., *"Summarize your security boundaries"*).
  5. While the response generates, click **Stop current request** to halt generation and return to ready state.

### Check 3: Tool Approvals and Action Tiers
- **Automated baseline**: SecureRunner confirmation tokens and single-use approval policies enforced in backend.
- **Manual steps**:
  1. Submit a prompt that requests a safe diagnostic (Tier 1, e.g. system watch/memory usage). Verify it executes automatically.
  2. Submit a request that reads an existing workspace file (Tier 2). Verify that an approval dialog appears with the specific target and purpose. Click **Deny** first, then re-run and click **Approve**.
  3. Submit a request to modify a workspace document (Tier 3). Verify that an action preview appears. If prompted, enter your **Owner PIN**. (Note: If your PIN was verified within the last 5 minutes, authorization is reused without re-prompting; verify that the action proceeds cleanly).

### Check 4: Document Preparation and Search
- **Note**: This check creates local document test rows in your encrypted database.
- **Manual steps**:
  1. Open **Workspace** → **Documents** tab.
  2. Click **New document**, enter a title (e.g. `Acceptance Note`), enter text, and click **Save**.
  3. Under **Search method**, choose **All words** (Keyword) and search for words from your note. Verify instant lexical matching.
  4. Choose **Meaning (English)**. If unindexed, click **Prepare next document** (indexes one document per click; verify the progress text `X of Y documents ready for meaning search (English)`).
  5. Search using conceptual synonyms and verify the result list.

### Check 5: Windows Voice Replies and Dictation
- **Automated baseline**: Windows speech API integration and WAV encoder unit tests pass.
- **Manual steps**:
  1. Go to **Settings** → **Voice**.
  2. Select an installed voice from the dropdown, adjust the **Speed** slider, and click **Preview voice**. Verify clear audio output through your speakers/headphones.
  3. Return to **Console**, click the speaker icon to set **Voice On**.
  4. Click the microphone button (**Start dictating**), speak a short phrase, and click the square stop button.
  5. **Review before send**: Verify that transcribed text appears in the input field without being sent automatically. Review and edit the text manually before submitting.

### Check 6: Emergency Controls and Offline Guard
- **Automated baseline**: Backend egress socket guard and network policy tests pass.
- **Manual steps**:
  1. Open **Settings**.
  2. Toggle **Offline mode** on.
  3. Verify that the System Status panel shows `Offline mode` with a green shield.
  4. In this mode, the software egress guard blocks outbound internet access at the backend layer.
  5. Toggle **Offline mode** off when finished.

### Check 7: Optional Read-Only Google Connection
- **Automated baseline**: Component tests in `settings-status.test.mjs` verify duplicate-request guards, credential size limit (<16 KB), format checks, and stale-success prevention.
- **Manual steps**:
  1. Open **Settings** → **Gmail and Google Calendar**.
  2. Inspect connection status: displays `Not configured` if no credentials have been imported.
  3. If you have created a desktop OAuth client in Google Cloud, click the file input to load the credentials JSON file. Verify that **Save credentials** appears only for valid files.
  4. Click **Save credentials** (prompts for PIN if not fresh).
  5. Use **Connect Google** to open the 5-minute authentication link in your browser.
  6. Return and click **Finish connection**.
  7. Click **Refresh Gmail** (fetches up to 10 inbox previews) and **Refresh Calendar** (fetches up to 25 events).
  8. *Privacy boundary*: Verify that remote write operations (sending email, modifying events) are currently unsupported; drafts stay locally in Workspace.

### Check 8: Encrypted Backup Creation & Download
- **Note**: This check creates an encrypted backup archive file.
- **Manual steps**:
  1. Open **Settings** → **Backup**.
  2. Click **Create backup now** (enter PIN if prompted; if PIN was recently verified, authorization is reused).
  3. Verify that a new entry appears in the list with the current timestamp and size.
  4. Click **Save a copy…** next to the backup. If prompted for PIN, enter your exact PIN.
  5. Verify that your browser/file picker prompts for a download location to save the `.enc` file (e.g. to a USB drive).
  6. Verify that cancelling the PIN prompt reports `"Operation cancelled."` and clears pending work without creating or downloading backups.

---

## 3. Isolated-Profile / Clean-Machine Restore Protocol

> [!CAUTION]
> **Do not run restore tests on your primary active installation.**
> Restoring replaces the current SQLCipher database and encryption keys with the backup's contents.

### Procedure for Staging / Isolated Machine:
1. Install Sentinel on a secondary PC or in a separate Windows user profile.
2. Launch Sentinel and navigate to the Lock screen (click **Lock Sentinel**).
3. Click **Restore from a backup**.
4. Select the `.enc` backup file created in Check 8.
5. Provide the secret:
   - **Same PC**: Enter the Owner PIN used when creating the backup.
   - **New PC**: Enter the recovery key recorded during initial setup (hyphenated base32 string, e.g. `ABCD-EFGH-...`).
6. Verify that Sentinel successfully unlocks and that all documents, chat history, and settings from the backup are restored.

---

## 4. Capability Verification Matrix

| Capability | Automated Test Status | Manual Verification Method | Verified Limitations / Roadmap Notice |
|---|---|---|---|
| **Encrypted Database** | Passed (`pytest`, SQLCipher memory & lock tests) | Check 1 (PIN unlock) | Encrypted with SQLCipher (Argon2id + DPAPI pinwrap); OS virtual memory paging applies |
| **Local LLM Chat** | Passed (backend test suite) | Check 2 (Typed chat) | Requires compatible local GGUF model; no cloud API fallback |
| **Tool Approvals** | Passed (SecureRunner unit tests) | Check 3 (Tier 1/2/3 prompts) | Approval required for read/write/execute actions |
| **Calculation Isolation** | Passed (T-16 Windows job worker tests) | Automated only | 4 math tools isolated in child processes; other skills in-process |
| **Meaning Search** | Passed (semantic search smoke) | Check 4 (Workspace documents) | Uses local pinned `bge-small-en-v1.5`; indexes one doc per click |
| **Voice TTS/STT** | Passed (WAV encoding tests) | Check 5 (Voice settings & mic) | Local Windows speech; wake-words and voice identity unverified |
| **Offline Egress Guard** | Passed (egress socket filters) | Check 6 (Offline toggle) | Software network proxy layer; not a hardware firewall |
| **Google Read-Only** | Passed (`settings-status.test.mjs`) | Check 7 (OAuth import) | Read-only; email sending and calendar editing currently unsupported |
| **Encrypted Backup** | Passed (`settings-retry.test.mjs`) | Check 8 (Create & Save) | Retains last 5 local backups; offsite copies recommended |
| **Clean Machine Setup**| Installer built (`SENTINEL Setup 1.0.0.exe`) | Section 3 (Secondary machine) | Requires end-to-end testing on unconfigured Windows PC |
| **Biometric Unlock** | None (unimplemented) | N/A | Windows Hello is not yet integrated; PIN/recovery key authoritative |
