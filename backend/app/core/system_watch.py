"""System Watch: notices when the PC looks wrong and tells the owner what to do.

It does not claim the PC is safe. It compares what it sees now with what the owner accepted as
normal (the baseline) and checks a few states that should always hold (Defender on, firewall on,
Sentinel's own files intact). All checks are read-only and use Windows' own tools. The only
automatic reaction is reversible: switching Sentinel to Offline mode on a critical alert.
Nothing is deleted, stopped or reconfigured without the owner. Works alongside Windows Defender,
not instead of it; malware that hides from every user program can hide from this too.
"""
import json
import os
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

# One fixed, read-only script (no interpolation). Every section is wrapped so one failing
# cmdlet (e.g. Defender cmdlets missing) does not hide the others.
COLLECT_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$r = [ordered]@{}
$startup = @{}
foreach ($k in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Run',
               'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce','HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce',
               'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run') {
  $p = Get-ItemProperty -Path $k
  if ($p) { $p.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object { $startup["$k\$($_.Name)"] = [string]$_.Value } }
}
foreach ($f in @([Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup'))) {
  if ($f) { Get-ChildItem -LiteralPath $f -File | ForEach-Object { $startup["folder\$($_.Name)"] = $_.FullName } }
}
$r.startup = $startup
$tasks = @{}
Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' -and $_.TaskPath -notlike '\Microsoft\*' } | ForEach-Object {
  $tasks["$($_.TaskPath)$($_.TaskName)"] = (($_.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)".Trim() }) -join ' ; ')
}
$r.tasks = $tasks
$services = @{}
Get-CimInstance Win32_Service | Where-Object { $_.StartMode -eq 'Auto' } | ForEach-Object { $services[$_.Name] = [string]$_.PathName }
$r.services = $services
$admins = @{}
Get-LocalGroupMember -SID 'S-1-5-32-544' | ForEach-Object { $admins[[string]$_.Name] = [string]$_.ObjectClass }
$r.admins = $admins
$fw = @{}
Get-NetFirewallProfile | ForEach-Object { $fw[[string]$_.Name] = [bool]$_.Enabled }
$r.firewall = $fw
$mp = Get-MpComputerStatus
if ($mp) {
  $r.defender = [ordered]@{ present = $true; antivirus = [bool]$mp.AntivirusEnabled; realtime = [bool]$mp.RealTimeProtectionEnabled;
                            signature_age_days = [int]$mp.AntivirusSignatureAge; tamper = [bool]$mp.IsTamperProtected }
} else { $r.defender = @{ present = $false } }
$threats = @()
Get-MpThreatDetection | Where-Object { $_.InitialDetectionTime -gt (Get-Date).AddDays(-7) } | ForEach-Object {
  $threats += [ordered]@{ id = [string]$_.DetectionID; threat = [string]$_.ThreatID; resources = (($_.Resources | Select-Object -First 3) -join ' ; ');
                          when = $_.InitialDetectionTime.ToString('o'); action_success = [bool]$_.ActionSuccess }
}
$r.threats = $threats
$r | ConvertTo-Json -Depth 4 -Compress
"""

POWERSHELL = r"c:\windows\system32\windowspowershell\v1.0\powershell.exe"
BASELINE_CATEGORIES = ("startup", "tasks", "services", "admins")
SUSPICIOUS_DIRS = ("\\downloads\\", "\\appdata\\local\\temp\\", "\\windows\\temp\\", "\\users\\public\\")

CATEGORY_TEXT = {
    "startup": ("New program set to start with Windows", [
        "If you did not just install something that does this, do not enter passwords until checked.",
        "Run a Windows Defender quick scan (button below).",
        "If you do not recognise it: Task Manager → Startup apps → Disable it.",
        "If you installed it yourself, choose \"This is fine\"."]),
    "tasks": ("New scheduled task", [
        "Scheduled tasks can start programs silently. Check the program it runs (shown above).",
        "Run a Windows Defender quick scan.",
        "If you do not recognise it: open Task Scheduler and disable the task.",
        "If it belongs to software you installed, choose \"This is fine\"."]),
    "services": ("New automatic Windows service", [
        "Services run with high privileges. Check the program path shown above.",
        "Run a Windows Defender quick scan.",
        "If you did not install new software, ask someone you trust before changing services.",
        "If it belongs to software you installed, choose \"This is fine\"."]),
    "admins": ("New administrator account", [
        "An unexpected administrator account is a serious warning sign.",
        "Do not sign in to banking or email on this PC until it is checked.",
        "Open Settings → Accounts → Other users and review the account.",
        "Change your Windows password from a different, trusted device if the account is unknown."]),
}


def _alert(category, key, severity, title, detail, steps):
    return {"id": f"{category}:{key}", "category": category, "key": key, "severity": severity,
            "title": title, "detail": detail, "steps": steps}


def analyze(snapshot: dict, baseline: Dict[str, Dict[str, str]], accepted_ids: set) -> List[dict]:
    """Pure function: what looks off in `snapshot` compared with the baseline.
    `baseline` maps category -> {key: detail}; `accepted_ids` are alert ids the owner marked fine."""
    alerts = []
    for category in BASELINE_CATEGORIES:
        known = baseline.get(category, {})
        for key, detail in (snapshot.get(category) or {}).items():
            detail = str(detail)
            if key not in known:
                title, steps = CATEGORY_TEXT[category]
                severity = "critical" if category == "admins" else "warning"
                lowered = detail.lower()
                if any(d in lowered for d in SUSPICIOUS_DIRS):
                    severity = "critical"
                    steps = ["It runs from a Downloads/Temp/Public folder, which legitimate software rarely does."] + steps
                alerts.append(_alert(category, key, severity, f"{title}: {key.split(chr(92))[-1]}", detail, steps))
            elif known[key] != detail:
                title, steps = CATEGORY_TEXT[category]
                alerts.append(_alert(category, key + "#changed", "warning", f"Changed: {key.split(chr(92))[-1]}",
                                     f"Was: {known[key]}\nNow: {detail}", steps))

    defender = snapshot.get("defender") or {}
    if not defender.get("present"):
        alerts.append(_alert("defender", "missing", "warning", "Windows Defender status could not be read",
                             "Another antivirus may be in charge, or Defender is unavailable.",
                             ["Open Windows Security → Virus & threat protection and confirm protection is on."]))
    else:
        if not defender.get("antivirus") or not defender.get("realtime"):
            alerts.append(_alert("defender", "realtime_off", "critical", "Windows Defender real-time protection is off",
                                 "Malware is sometimes able to switch this off.",
                                 ["Open Windows Security → Virus & threat protection → Manage settings → turn Real-time protection on.",
                                  "If it turns itself off again, treat the PC as possibly infected and run a Microsoft Defender Offline scan."]))
        if int(defender.get("signature_age_days") or 0) > 7:
            alerts.append(_alert("defender", "signatures_old", "warning", "Defender virus definitions are out of date",
                                 f"Last update {defender.get('signature_age_days')} days ago.",
                                 ["Open Windows Security → Virus & threat protection → Check for updates."]))
    for threat in snapshot.get("threats") or []:
        handled = threat.get("action_success")
        alerts.append(_alert("threat", str(threat.get("id")), "warning" if handled else "critical",
                             "Windows Defender found a threat" + ("" if handled else " that is not resolved"),
                             f"{threat.get('resources', '')} (detected {threat.get('when', '')})",
                             ["Open Windows Security → Protection history and review the item.",
                              "Run a Windows Defender full scan.",
                              "If it was not removed, run a Microsoft Defender Offline scan."]))
    for name, enabled in (snapshot.get("firewall") or {}).items():
        if enabled is False:
            alerts.append(_alert("firewall", name, "critical", f"Windows Firewall is off ({name} profile)", "",
                                 ["Open Windows Security → Firewall & network protection and turn it on for this profile."]))
    for proc in snapshot.get("suspicious_processes") or []:
        alerts.append(_alert("process", proc["exe"].lower(), "warning",
                             f"Program running from a download/temp folder: {os.path.basename(proc['exe'])}",
                             f"{proc['exe']}" + (" — it has internet connections" if proc.get("network") else ""),
                             ["If you did not start this program on purpose, close it from Task Manager.",
                              "Run a Windows Defender quick scan.",
                              "If you started it yourself and trust it, choose \"This is fine\"."]))
    for problem in snapshot.get("self_integrity") or []:
        alerts.append(_alert("sentinel", problem["key"], "critical", "Sentinel's own files were changed", problem["detail"],
                             ["Sentinel switched itself to Offline mode as a precaution.",
                              "If you did not update Sentinel, run a Windows Defender full scan.",
                              "Reinstall Sentinel from a trusted copy before unlocking sensitive data again."]))
    return [a for a in alerts if a["id"] not in accepted_ids]


def collect_processes() -> List[dict]:
    import psutil
    found = {}
    try:
        connected = {c.pid for c in psutil.net_connections(kind="inet") if c.raddr and c.pid}
    except Exception:
        connected = set()
    for proc in psutil.process_iter(["pid", "exe"]):
        exe = (proc.info.get("exe") or "")
        if exe and any(d in exe.lower() for d in SUSPICIOUS_DIRS):
            entry = found.setdefault(exe.lower(), {"exe": exe, "network": False})
            entry["network"] = entry["network"] or proc.info["pid"] in connected
    return list(found.values())


def self_integrity() -> List[dict]:
    problems = []
    try:
        from app.core.skill_verifier import skill_verifier
        pins = skill_verifier.pinned_hashes()
        if pins is None:
            problems.append({"key": "skill_pins", "detail": "The skill hash list is missing or unreadable."})
        else:
            for entry, expected in pins.items():
                if skill_verifier._compute_module_hash(entry) != expected:
                    problems.append({"key": f"skill:{entry}", "detail": f"Skill file {entry} does not match its recorded fingerprint."})
    except Exception as e:
        problems.append({"key": "skill_check", "detail": f"Skill check failed: {type(e).__name__}"})
    try:
        from app.core.audit_logger import audit_logger
        result = audit_logger.verify_log()
        if not result["ok"]:
            problems.append({"key": "audit_log", "detail": f"Audit log tampering detected: {result['problem']}"})
    except Exception as e:
        problems.append({"key": "audit_check", "detail": f"Audit check failed: {type(e).__name__}"})
    return problems


def collect() -> dict:
    """Takes a snapshot. Windows-only parts are skipped elsewhere."""
    snapshot = {}
    if os.name == "nt":
        from app.core.safe_process import safe_process
        ok, out, err = safe_process.run_command(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", COLLECT_SCRIPT],
            timeout_seconds=120, job_id="system-watch", keep_bytes=900 * 1024)
        if ok and out.strip():
            try:
                snapshot = json.loads(out)
            except ValueError:
                snapshot = {"collect_error": "unreadable output"}
        else:
            snapshot = {"collect_error": (err or "collection failed")[:200]}
    snapshot["suspicious_processes"] = collect_processes()
    snapshot["self_integrity"] = self_integrity()
    return snapshot


class SystemWatch:
    INTERVAL_SECONDS = 15 * 60

    def __init__(self):
        self._lock = threading.Lock()
        self.last_run: Optional[float] = None
        self.last_error: Optional[str] = None

    # ── storage (encrypted database) ─────────────────────────────
    def _baseline(self, db) -> Dict[str, Dict[str, str]]:
        from app.db.models import WatchBaseline
        result: Dict[str, Dict[str, str]] = {}
        for row in db.query(WatchBaseline).all():
            result.setdefault(row.category, {})[row.key] = row.detail
        return result

    def _set_baseline(self, db, category, key, detail):
        from app.db.models import WatchBaseline
        row_id = f"{category}:{key}"
        row = db.get(WatchBaseline, row_id)
        if row is None:
            db.add(WatchBaseline(id=row_id, category=category, key=key, detail=detail))
        else:
            row.detail, row.accepted_at = detail, datetime.utcnow()

    def has_baseline(self, db) -> bool:
        from app.db.models import WatchBaseline
        return db.query(WatchBaseline).first() is not None

    def run_check(self, snapshot: Optional[dict] = None) -> dict:
        """Collects (unless a snapshot is given), compares, stores alerts. Returns a summary."""
        from app.db.database import SessionLocal
        from app.db.models import WatchAlert
        if not self._lock.acquire(blocking=False):
            return {"status": "busy"}
        try:
            snapshot = collect() if snapshot is None else snapshot
            self.last_error = snapshot.get("collect_error")
            with SessionLocal() as db:
                first_run = not self.has_baseline(db)
                if first_run:
                    # The first snapshot becomes "normal". It cannot judge what was already there.
                    for category in BASELINE_CATEGORIES:
                        for key, detail in (snapshot.get(category) or {}).items():
                            self._set_baseline(db, category, key, str(detail))
                    db.commit()
                accepted = {row.id for row in db.query(WatchAlert).filter(WatchAlert.status == "accepted")}
                alerts = analyze(snapshot, self._baseline(db), accepted)
                now = datetime.utcnow()
                current = {a["id"] for a in alerts}
                for a in alerts:
                    row = db.get(WatchAlert, a["id"])
                    if row is None:
                        db.add(WatchAlert(id=a["id"], category=a["category"], key=a["key"], severity=a["severity"],
                                          title=a["title"], detail=a["detail"], steps=json.dumps(a["steps"]),
                                          status="open", first_seen=now, last_seen=now))
                    else:
                        row.last_seen, row.severity, row.detail = now, a["severity"], a["detail"]
                        if row.status == "resolved":
                            row.status = "open"
                # Open alerts whose cause disappeared are marked resolved (kept for history).
                for row in db.query(WatchAlert).filter(WatchAlert.status == "open"):
                    if row.id not in current:
                        row.status = "resolved"
                db.commit()
                critical = [a for a in alerts if a["severity"] == "critical"]
            if critical:
                self._react_to_critical()
            self.last_run = time.time()
            return {"status": "ok", "first_run": first_run, "alerts": len(alerts), "critical": len(critical),
                    "collect_error": self.last_error}
        finally:
            self._lock.release()

    def _react_to_critical(self):
        """The only automatic reaction: Offline mode (the owner can turn it back off)."""
        try:
            from app.core.egress import egress_guard
            if not egress_guard.status().get("offline"):
                egress_guard.set_offline(True)
                from app.core.audit_logger import audit_logger
                audit_logger.log_event("system_watch_offline", {"reason": "critical alert"})
        except Exception:
            pass

    def accept(self, alert_id: str) -> bool:
        """Owner says "this is fine": the item joins the baseline and stops alerting."""
        from app.db.database import SessionLocal
        from app.db.models import WatchAlert
        with SessionLocal() as db:
            row = db.get(WatchAlert, alert_id)
            if row is None:
                return False
            row.status = "accepted"
            if row.category in BASELINE_CATEGORIES:
                key = row.key[:-len("#changed")] if row.key.endswith("#changed") else row.key
                detail = row.detail.split("\nNow: ", 1)[-1] if row.key.endswith("#changed") else row.detail
                self._set_baseline(db, row.category, key, detail)
                row.status = "resolved"   # baseline now covers it; a future change alerts again
            db.commit()
            return True

    def status(self) -> dict:
        from app.db.database import SessionLocal
        from app.db.models import WatchAlert
        with SessionLocal() as db:
            rows = db.query(WatchAlert).filter(WatchAlert.status == "open").order_by(WatchAlert.last_seen.desc()).all()
            alerts = [{"id": r.id, "severity": r.severity, "title": r.title, "detail": r.detail,
                       "steps": json.loads(r.steps or "[]"), "first_seen": r.first_seen.isoformat() + "Z",
                       "category": r.category} for r in rows]
            baseline = self.has_baseline(db)
        critical = sum(a["severity"] == "critical" for a in alerts)
        if not baseline:
            summary = "System Watch has not run yet."
        elif critical:
            summary = f"{critical} serious issue(s) need your attention."
        elif alerts:
            summary = f"{len(alerts)} thing(s) to review."
        else:
            summary = "Nothing unusual found in the last check."
        return {"summary": summary, "alerts": alerts, "last_run": self.last_run, "collect_error": self.last_error,
                "note": "System Watch notices changes and unsafe settings. It is not an antivirus and cannot prove the PC is clean."}

    def due(self) -> bool:
        return self.last_run is None or time.time() - self.last_run >= self.INTERVAL_SECONDS


system_watch = SystemWatch()
