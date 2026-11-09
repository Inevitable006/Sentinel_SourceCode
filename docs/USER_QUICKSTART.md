# Sentinel Owner Quickstart & Recovery Guide

Sentinel is a private, local-first personal AI assistant for one owner on Windows. All reasoning, document search, and memory storage run directly on your PC. No cloud AI APIs or telemetry services are used. Your data is stored in an encrypted database (SQLCipher) protected by your PIN.

---

## 1. First-Run Setup: Owner PIN and Recovery Key

When you open Sentinel for the first time, you will see the initial setup screen:

1. **Choose a PIN**:
   - Enter a secure PIN (at least 8 characters, or 10+ digits if using numbers only).
   - Retype the PIN in the confirmation field.
   - Optional: Leave "Remove test rows" checked to start with clean private tables.
   - Click **Set PIN and initialize encrypted storage**.
2. **Save Your Recovery Key**:
   - Sentinel displays a recovery key formatted in hyphenated groups (base32 string, e.g., `ABCD-EFGH-...`).
   - Copy or write this key down exactly as displayed and store it in your password manager.
   - Check **I wrote down or saved this recovery key**.
   - Click **Open Sentinel**.
   - *Important*: Keep this key safe offline. If you ever forget your PIN or move backups to a new PC, this key is the only way to recover your data. Never paste your recovery key into chat or send it online.

---

## 2. Local AI Model Availability & First Typed Chat

1. In the left navigation menu, click **Console** (the main chat screen).
2. Check the header indicators:
   - **Core AI Processor**: Displays `Connected` when the local backend is ready.
   - **Model state**: If it shows `Load Local Model`, click it to load your local LLM into memory. The badge changes to `Loading...` and then `Model Ready`.
   - To change model profiles, go to **Settings** → **Model Selection** and select from downloaded profiles.
3. **Type a Message**:
   - Type a prompt into the chat input (for example: *"What can you help me with today?"*).
   - Press **Enter** or click the send button.
   - While Sentinel is thinking, you can click **Stop current request** at any time to request cancellation and stop generation.

---

## 3. Tool Approvals and Safety Tiers

Sentinel classifies all automated actions into risk tiers:

- **Tier 1 (Safe diagnostics)**: System health, CPU/RAM readings, and governor state run automatically.
- **Tier 2 (Confidential read-only)**: Reading your code, notes, or saved documents requires your explicit confirmation. Sentinel displays an approval dialog with the purpose and file arguments. Click **Approve** or **Deny**.
- **Tier 3 (Modifications & Execution)**: Writing files, deleting files, or running Python scripts displays an action preview (including what will change and how to undo it). These require entering your **Owner PIN** to approve.
- **Fresh-PIN 5-Minute Window**: When you enter your PIN for a sensitive Tier 3 action, authorization remains fresh for five minutes from successful verification (not inactivity). Subsequent sensitive actions within this 5-minute window reuse that authorization without prompting you for the PIN again. After five minutes from verification or whenever Sentinel is locked, PIN re-verification is required.
- **5-Minute Undo**: File modifications record an undo snapshot that can be rolled back from **Workspace** → **File actions**.

---

## 4. Saving and Searching Documents

1. In the sidebar, click **Workspace** → **Documents** tab.
2. Click **New document**, enter a title and text, and click **Save**.
3. **Search Modes**:
   - **All words (Keyword)**: Fast lexical search powered by the encrypted SQLCipher FTS5 full-text index.
   - **Meaning (English)**: Conceptual search powered by Sentinel's local, pinned `bge-small-en-v1.5` GGUF embedding model.
   - If documents are not yet indexed for meaning search, click **Prepare next document** (indexes one document per click; the indicator shows how many documents are ready, e.g. `X of Y documents ready for meaning search (English)`).
4. *Reference*: For technical details on the encrypted index and chunk vectors, see [DOCUMENT_SEARCH.md](DOCUMENT_SEARCH.md).

---

## 5. Voice Replies and Local Dictation

1. **Spoken Replies (TTS)**:
   - In the **Console** header, click the speaker icon to toggle between **Voice On** and **Voice Off**.
   - To configure voices: Go to **Settings** → **Voice**, choose an installed Windows voice from the dropdown, adjust the **Speed** slider, and click **Preview voice**.
2. **Local Dictation (STT)**:
   - In the **Console** input bar, click the microphone button (**Start dictating**).
   - Speak your prompt (up to 30 seconds).
   - Click the square button to finish, or the **X** button to discard the audio.
   - Sentinel transcribes the audio locally and puts the text into your input field.
   - *Review before send*: Dictated text is never sent automatically. You can review, edit, or delete the text before pressing send.
3. *Reference*: See [VOICE.md](VOICE.md) for supported Windows speech components.

---

## 6. Optional Google Workspace Connection (Read-Only)

Sentinel can read inbox message previews and upcoming primary calendar events to help you organize drafts locally.

1. Go to **Settings** → **Gmail and Google Calendar**.
2. Create a desktop OAuth client in your Google Cloud project (enable Gmail and Google Calendar APIs in read-only mode).
3. Under **Desktop OAuth credentials**, click the file input to upload your downloaded credentials JSON file. *Never paste credentials into a chat.*
4. Click **Save credentials** (prompts for PIN).
5. Click **Connect Google** and copy the 5-minute sign-in link into your standard browser to authenticate.
6. Return to Sentinel and click **Finish connection** (prompts for PIN).
7. Use **Refresh Gmail** (fetches up to 10 inbox previews) and **Refresh Calendar** (fetches up to 25 events for the next 7 days).
8. **Strict Privacy Boundary**: This connection is strictly read-only. Sentinel cannot send emails, delete messages, or create/modify remote calendar events (remote write operations are currently unsupported; drafts remain locally in Sentinel Workspace).
9. *Reference*: See [GOOGLE.md](GOOGLE.md) for Google Cloud setup steps.

---

## 7. Backups and Safe Recovery

1. **Creating a Backup**:
   - Go to **Settings** → **Backup**.
   - Click **Create backup now** (enter your PIN if prompted).
   - A backup archive is created holding your encrypted database, memories, tasks, portfolio, and settings.
   - Click **Save a copy…** next to any backup in the list to export it to external storage (such as a USB drive).
2. **Restoring on This or Another PC**:
   - Lock Sentinel by clicking **Lock Sentinel** in the sidebar.
   - On the lock screen, click **Restore from a backup**.
   - Select the backup file and enter your PIN (on the same PC) or your **Recovery Key** (if restoring on a new PC).

---

## 8. Emergency Controls & Diagnostics

- **Lock Sentinel**: Click **Lock Sentinel** in the lower-left sidebar anytime. The encrypted database closes immediately and active session keys are cleared from application memory.
- **Offline Mode**: In **Settings**, toggle **Offline mode** on. This software egress guard blocks outbound internet access at the backend network layer. Check the **Privacy** widget on the right sidebar to confirm network state.
- **Component Readiness**: In **Settings** → **Component Readiness**, inspect the live status of Chat, Dictation, Voice, Document search, Google, and Backup.
- **Logs**: If an issue occurs, inspect logs in `%APPDATA%\sentinel\logs\`. Tokens, passwords, and database keys are automatically masked before writing.

---

## 9. Non-Destructive Owner Acceptance Checklist

Use this checklist to verify your installation without altering existing production data:

- [ ] **Unlock & Lock**: Click **Lock Sentinel** in the sidebar. Enter your PIN on the lock screen to verify successful unlock.
- [ ] **Readiness Check**: In **Settings** → **Component Readiness**, click **Refresh status** and verify that local components report their status honestly.
- [ ] **Voice Preview**: In **Settings** → **Voice**, click **Preview voice** and confirm Windows speech audio plays.
- [ ] **Console Chat**: In **Console**, confirm `Model Ready` appears, submit a simple prompt, and receive a response.
- [ ] **Document Creation**: In **Workspace** → **Documents**, create a test note (*creates a local note in your encrypted database*), then search for it using **All words** or **Meaning (English)** modes.
- [ ] **Backup Verification**: In **Settings** → **Backup**, click **Create backup now** (*creates an encrypted `.enc` backup file*) and verify that a new timestamped backup entry appears in the list.
- [ ] **Offline Guard**: In **Settings**, turn on **Offline mode**. Check that the System Status panel shows `Offline mode` with a green shield.

*Detailed Protocol*: For full interactive verification protocols, capability status matrices, and isolated clean-machine restore testing instructions, see [OWNER_ACCEPTANCE.md](OWNER_ACCEPTANCE.md). Never restore test backups over your primary active profile.

---

## 10. Honest Limitations & Roadmap Notice

- **Speech & Wake Words**: Hands-free wake word detection and voice enrollment (speaker identity) are not implemented. All dictation is initiated manually by clicking the microphone button.
- **Windows Hello**: Biometric unlock requires supported hardware and is not yet integrated; PIN and recovery key are the authoritative unlock mechanisms.
- **Google Interaction**: Email sending, message deletion, and calendar modifications are currently unsupported; drafts remain locally in Sentinel Workspace.
- **Clean-Machine Installation**: The packaged installer (`dist/SENTINEL Setup 1.0.0.exe`) bundles verified runtimes, but bare-metal installation on unconfigured machines requires owner environment testing.
