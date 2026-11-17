# Hardware-Abnahme vor produktiver Nutzung

Softwaretests ersetzen diese Prüfung nicht. Papier zunächst aufbewahren.

## Voraussetzungen

- Frische Raspberry Pi OS Lite 64-bit Installation auf Pi 3B+ bzw. Pi 4B.
- Exakte OS-Version (`cat /etc/os-release`), Kernel (`uname -r`), SANE (`scanimage --version`), Paperless-Version dokumentieren. Nur öffentliche Versionsdaten teilen, keine Konfigurationsdatei/Token.
- iX500 am eigenen Netzteil, USB angeschlossen, aufgeklappt.
- Installer interaktiv erfolgreich ausführen; Dienste und Rechte kontrollieren.

## Prüffälle

1. **Grundbetrieb:** Zwei A4-Blätter mit deutlich unterscheidbarer Vorder-/Rückseite scannen. Ein PDF, vier Seiten in der erwarteten Reihenfolge, vollständige Ränder, lesbare kleine Schrift. Hardwaretaste separat testen, nicht nur manuellen Aufruf.
2. **Paperless:** Dokument sichtbar, OCR/Archiv verarbeitet, passende Task-ID in `receipt.json`, Job wechselt von `submitted` nach `sent`. Die Scanner-Identität kann das Dokument lesen; Schreib-/Taskrechte tatsächlich geprüft.
3. **Neustart:** Pi neu starten, ohne Benutzeranmeldung Taste testen. Scanner geschlossen/offline beim Pi-Start, danach aufklappen; Dienst erholt sich.
4. **WLAN/SSH:** Gewähltes Profil nach Neustart aktiv. Anmeldung als eingerichteter Benutzer aus zweiter Sitzung prüfen. Passwort-/Schlüsselrichtlinie mit `sudo sshd -T -C user=BENUTZER,host=HOST,addr=CLIENT_IP` kontrollieren. Keine Zugangsdaten in Supportausgaben.
5. **Leerseitenfilter:** Erst `0`, dann optional `0.05`: normaler Text, nur eine kleine Unterschrift, blasse Schrift, Stempel, echte leere Rückseite. `original.pdf` gegen gefiltertes PDF vergleichen. Bei Fehlklassifikation Filter deaktivieren.
6. **Offline:** Paperless-Verbindung vor dem Upload sperren/Server stoppen. Scan bleibt in `pending`, nach Wiederherstellung wird er importiert. Bei absichtlich unterbrochener bereits laufender POST-Verbindung `uncertain` erwarten; vor Wiederholung Server prüfen.
7. **Fehler:** Leerer ADF und echte Scannerstörung kontrolliert prüfen (keinen Stau absichtlich erzwingen). Teilscan wird niemals automatisch hochgeladen; Diagnose und Seiten bleiben lokal. Ganzen Stapel nach Behebung neu scannen.
8. **Berechtigungen/TLS:** Falscher Token führt zu 401/403 und erhaltenem PDF. Ungültiges Serverzertifikat führt zu Verbindungswarnung; kein Umgehen der TLS-Prüfung. Richtige CA/URL behebt das Problem.
9. **Last/Speicher:** Kleiner, danach üblicher Stapel in Farbe 200/300 dpi. Laufzeit, RAM und SD-Platz prüfen. Kein Dienstabbruch, Seitenzahl korrekt. Größere Stapel erst nach erfolgreicher Messung.
10. **Deinstallation:** Auf einem Testsystem deinstallieren. Dienste/Regeln weg, Papier/PDFs, Adminzugang und Konfiguration erhalten. Keine Beeinträchtigung fremder Scandienste.

## Freigabeprotokoll

Öffentliche Hardwaretest-Ergebnisse dürfen Modell, OS-/SANE-/Paperless-Version, Profil, getestete Seitenzahl, Laufzeit und PASS/FAIL enthalten. Dokumente, Netzwerkdaten, Seriennummern und Tokens auslassen. Eine erste Veröffentlichung kann als Vorabversion erfolgen; „auf Hardware getestet“ erst nach dieser Abnahme ergänzen.
