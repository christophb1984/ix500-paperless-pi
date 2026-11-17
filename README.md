# ix500-paperless-pi

Headless Scan-Appliance für den **Fujitsu ScanSnap iX500**: Papier einlegen, blaue Taste drücken, PDF automatisch zu **Paperless-ngx** übertragen. Eine lokale Weboberfläche bietet Scanstart, Profile und Geräteeinstellungen – auch auf dem Handy.

**Version 0.2.5 · MIT · Raspberry Pi OS Lite 64-bit**

Frühe Version für ein vertrauenswürdiges Heimnetz. Ein funktionierender iX500-/Paperless-Grundbetrieb wurde aus einer realen Installation bestätigt; es gibt noch keine vollständige Hardware-Testmatrix für alle Zielsysteme. Vor produktiver Nutzung die [Abnahme](docs/ACCEPTANCE.md) durchführen. Dieses Repository enthält Quellcode, kein flashbares SD-Image.

## Funktionen

- Hardwaretaste und Browser verwenden denselben Scanworker; kein konkurrierender USB-Zugriff.
- Einseitig, zweiseitig oder **Automatisch**: physischer Duplexscan, danach Entfernen leerer Seiten anhand einstellbarer Grenzwerte.
- Farbe, Graustufen, Schwarzweiß, 100–600 dpi, A4/Legal/eigener fester Bereich und PDF-Bildqualität.
- Native SANE-Optionen mit tatsächlichen Gerätewerten, Auswahlmöglichkeiten und Grenzen. Verfügbare Werte hängen von Scanner und Modus ab.
- Gespeicherte Profile für die blaue Taste; Browser-Aufträge verwenden eine unveränderliche Kopie der angezeigten Einstellungen.
- Lokale Warteschlange, Task-Verfolgung über die Paperless-API, geschützte Zugangsdaten und systemd-Dienste.
- Bei entfernten Leerseiten zusätzlich ein vollständiges Original-PDF. Fehlerhafte und unklar beantwortete Aufträge bleiben lokal erhalten.

```text
ScanSnap iX500 ── USB ── Raspberry Pi / SANE
                                  │
                     Taste oder lokale Weboberfläche
                                  │
                         PDF + lokale Warteschlange
                                  │
                         Paperless-ngx API → OCR
```

## Voraussetzungen

- Raspberry Pi **3B+ oder 4B**, Raspberry Pi OS Lite **arm64**, Bookworm oder Trixie.
- iX500 mit eigenem Netzteil und USB-Kabel; aufgeklappt/eingeschaltet.
- Bestehender SSH-/Netzwerkzugang und Internetzugang für die Paketinstallation.
- Paperless-ngx mit API-Token sowie Dokument- und Task-Berechtigungen für den Scanner-Benutzer.

Der Scanner selbst wird per USB angesprochen; sein WLAN wird hier nicht unterstützt. Der Pi kann Ethernet oder WLAN nutzen. OCR läuft auf dem Paperless-Server. Für den Pi 3B+ mit Farbe/200 dpi und kleinen Stapeln beginnen; 300 dpi und große Stapel erhöhen Laufzeit, RAM- und SD-Bedarf.

## Installation

1. Offizielles Raspberry Pi OS Lite 64-bit mit **Raspberry Pi Imager** flashen. Dort Benutzer, SSH, Hostname und bei Bedarf WLAN einrichten. Der private SSH-Schlüssel bleibt auf dem Client; am Pi wird der öffentliche Schlüssel hinterlegt.
2. Per SSH oder lokal am Pi anmelden. Der Installer kann einen noch nicht erreichbaren Pi nicht erstmals ins Netzwerk bringen.
3. Auf dem Pi:

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/christophb1984/ix500-paperless-pi.git
cd ix500-paperless-pi
sudo bash install.sh
```

Der Assistent fragt nach Netzwerk, Hostname, Benutzer/SSH, Paperless-URL/Token und Scanprofil. Bei bereits funktionierender Verbindung **behalten** wählen. Danach ein separates Webpasswort festlegen; Standardport ist **8080**.

Die Paperless-Basis-URL ohne `/api` eingeben, z. B. `https://paperless.example.org`. Ein Unterpfad ist möglich. Den API-Token in **Mein Profil / My Profile** in Paperless erzeugen. Ein separater Benutzer sollte Dokumente lesen/hinzufügen und die zugehörigen Tasks lesen können. Die konkreten Rechte mit dem ersten Testupload prüfen.

Das Skript wird als Datei ausgeführt; kein `curl | sudo bash`. Laufzeitpakete kommen aus apt: SANE, Pillow, img2pdf, python-sane, Flask, Waitress und curl. Keine root-pip-Installation auf Raspberry Pi OS.

## Weboberfläche und Profile

Im Browser `http://HOSTNAME.local:8080/` oder `http://PI-IP:8080/` öffnen und mit dem separaten Webpasswort anmelden.

- **Scan starten** verwendet die aktuell angezeigten Werte einmalig.
- **Profil speichern & aktivieren** speichert diese Werte auch für die blaue Taste.
- **Für blaue Taste aktivieren** wählt ein vorhandenes gespeichertes Profil.
- **Geräteoptionen aktualisieren** fragt die für den gewählten Modus verfügbaren Werte ab; nicht aktive und reine Sensoroptionen bleiben zur Orientierung sichtbar.

[Ausführliche Web-Anleitung und Update](docs/WEB.md)

„Automatisch“ erkennt den Druck nicht vor dem Papierdurchlauf. Es scannt beide Seiten und entfernt danach als leer eingestufte Seiten. Ist der Filter ausgeschaltet, setzt die Webauswahl zunächst `0.1 %`; aktive Werte bleiben erhalten. Heller Durchdruck, blasse Schrift oder kleine Unterschriften können falsch bewertet werden. Original-PDF vergleichen und Grenzwerte mit eigenen Dokumenten kalibrieren.

## Vorhandene Installation aktualisieren

Wenn gerade kein Scan läuft:

```bash
cd ix500-paperless-pi
git pull --ff-only
sudo bash update.sh
```

Das Update behält Netzwerk-/SSH-Einstellungen, Paperless-Zugang und Jobs. Während des Dienststopps hält es dieselbe Startsperre wie der Scanworker. Ein aktiver/wartender Auftrag verhindert das Update. Separat gestartete Administrator-Scans und andere Verwaltungsbefehle während des Updates sind nicht unterstützt. Bei sehr alten Versionen ohne diesen Kontrollkanal muss der Scandienst zuerst bewusst im Leerlauf gestoppt werden.

Wurde die Anwendung ursprünglich aus einer ZIP installiert, das neue Archiv in einen Projektordner entpacken und dort `sudo bash update.sh` ausführen. Bei manuellen Änderungen an Programmdateien diese vor einem Update sichern. Eine spätere Störung rollt bereits ausgeführte Systemänderungen nicht pauschal zurück.

## Konfiguration und Daten

| Pfad | Inhalt |
| --- | --- |
| `/etc/ix500-paperless/config.json` | Root-Konfiguration und Paperless-Zugang; `root:ix500`, `0640` |
| `/etc/ix500-paperless/web.json` | Webpasswort-Hash, Sitzungsschlüssel und Port; `root:ix500`, `0640` |
| `/var/lib/ix500-paperless/control.json` | Aktives Profil und gespeicherte Scanwerte |
| `/var/lib/ix500-paperless/` | Warteschlange, PDFs und lokale Diagnose; `ix500`, `0700` |

[Konfigurationsbeispiel](config/config.example.json) enthält nur Platzhalter. Die Weboberfläche liefert keine Paperless-Tokens aus. Nach dem ersten Speichern sind die Webprofile für Scanwerte maßgeblich; direkte Änderungen an der Root-Konfiguration überschreiben sie nicht. Webzugang, Netzwerk und SSH werden nicht über die Scanoberfläche verwaltet.

HTTP verschlüsselt weder Webpasswort noch Dokumente. Die Standardinstallation ist für ein **vertrauenswürdiges LAN**, ohne Internet-Portfreigabe. Für Fernzugriff ein VPN oder passend eingerichtetes HTTPS verwenden. Paperless-HTTPS prüft Zertifikate; eigene CA-Datei bei Bedarf konfigurieren. Details zum Schutzmodell stehen in [SECURITY.md](SECURITY.md).

## Warteschlange

| Ordner | Bedeutung |
| --- | --- |
| `working` | Laufender Scan; nach einem Neustart zur Prüfung zurückgehalten |
| `pending` | Fertiges PDF, Upload wartet; Verbindungs-/TLS-Fehler werden später erneut versucht |
| `inflight` | POST läuft; nach Abbruch zunächst unklarer Status |
| `submitted` | Paperless hat eine Task-ID zurückgegeben, Import wird noch geprüft |
| `sent` | Paperless meldet erfolgreichen Import |
| `failed` | HTTP-Ablehnung oder Importfehler |
| `uncertain` | Unklarer Uploadstatus: vor Wiederholung Paperless prüfen |
| `interrupted` | Teilscan, Scanfehler, Verarbeitung abgebrochen oder nur leere Seiten |

Ein HTTP 200 allein bestätigt den Import noch nicht. Die Anwendung fragt den zurückgegebenen Paperless-Task ab. Es wird kein Dokumentdatum aus dem Scanzeitpunkt gesetzt; Paperless kann das Dokumentdatum ermitteln.

**Keine automatische Löschung:** Auch importierte PDFs bleiben lokal. Nach erfolgreicher Kontrolle und Backup einzelne `sent`-Jobs bewusst bereinigen. Ein zusätzliches `original.pdf` kann ausschließlich auf dem Pi vorliegen. Freier Platz wird vor jedem Scan geprüft; es gibt kein fortlaufendes Speicherquota während eines Stapels. Papier zunächst aufbewahren.

POST-Timeouts und unklare Antworten werden nicht blind wiederholt. Zwischen Pi und Server besteht keine Exactly-once-Garantie. `uncertain` deshalb vor Wiederholung im Server abgleichen. Teilscans werden nicht automatisch hochgeladen; nach Stau den vollständigen Stapel erneut scannen.

## Diagnose

```bash
sudo systemctl status ix500-scan.service ix500-upload.timer ix500-web.service
sudo journalctl -u ix500-scan.service -u ix500-upload.service -u ix500-web.service -n 60 --no-pager
sudo -u ix500 python3 /opt/ix500-paperless/appliance.py status
lsusb -d 04c5:132b
```

Scanner prüfen, während der Tastendienst gestoppt ist:

```bash
sudo systemctl stop ix500-scan.service
sudo -u ix500 scanimage -L
sudo systemctl start ix500-scan.service
```

- **Nicht bereit:** USB/Deckel/Strom und konkreten Profilfehler prüfen. Bei inkompatiblen nativen Optionen in der Weboberfläche Zusatzoptionen zurücksetzen und neu abfragen. Keine parallelen Scanprogramme/scanbd/saned verwenden.
- **401/403:** Token und Dokument-/Taskrechte prüfen. **404:** Basis-URL/Unterpfad. **413:** Reverse-Proxy-Größenlimit. **TLS:** Uhrzeit, Zertifikat, Hostname und CA prüfen; kein `curl -k`.
- **Web nicht erreichbar:** tatsächliche Pi-IP/Port, Dienst und vorhandene Firewall prüfen. Die Installation verändert keine Firewallregeln.
- **Bild abgeschnitten:** fester Scanbereich prüfen. Automatische Papierlänge/-drehung und Dokumenttrennung sind nicht implementiert. JPEG-Qualität 90 ist der Standard; kein verlustfreies Archivformat.

Webpasswort zurücksetzen:

```bash
sudo python3 /opt/ix500-paperless/setup_web.py
sudo systemctl restart ix500-web.service
```

## Deinstallation

```bash
sudo bash uninstall.sh
```

Entfernt Programmdateien, Dienste und eigene USB-/SANE-Regeln. Konfiguration, Tokens, Jobs, Pakete, System-/Adminbenutzer, Hostname sowie SSH-/Netzwerkeinstellungen bleiben erhalten. Vor Weitergabe eines Pi die Daten bewusst entfernen und den Paperless-Token widerrufen.

## Entwicklung und Tests

Unter Debian/Ubuntu:

```bash
sudo apt-get install python3-pil python3-img2pdf python3-pypdf python3-flask python3-waitress curl shellcheck
python3 -m unittest discover -s tests -v
bash -n install.sh update.sh uninstall.sh
shellcheck install.sh update.sh uninstall.sh
systemd-analyze verify systemd/ix500-scan.service systemd/ix500-upload.service systemd/ix500-upload.timer systemd/ix500-web.service
```

Auf anderen Entwicklungsrechnern eine virtuelle Umgebung mit `Pillow img2pdf pypdf Flask waitress` verwenden. HTTP-Tests benötigen Loopback-Sockets. Physisches USB wird simuliert; Bild-/PDF-Verarbeitung und HTTP-Client sind real. Optionale Chromium-Prüfung: [Web-Anleitung](docs/WEB.md#browserprüfung-für-entwickler-optional). [Prüfumfang und Grenzen](docs/VERIFICATION.md).

## Weitere Dokumentation

- [Hardware-Abnahme](docs/ACCEPTANCE.md)
- [Weboberfläche, Profile und Updates](docs/WEB.md)
- [Optionaler Image-Build](docs/IMAGE-BUILD.md)
- [Änderungen](CHANGELOG.md) · [Sicherheit](SECURITY.md) · [Beiträge](CONTRIBUTING.md)

## Lizenz und Quellen

[MIT](LICENSE). Keine Zugehörigkeit zu Fujitsu, Ricoh oder Paperless-ngx. Betriebssystem und installierte Drittanbieterpakete behalten ihre eigenen Lizenzen; das Repository enthält deren Quellcode nicht.

Der Ansatz wurde mit [ix500-linux](https://github.com/allardvdb/ix500-linux) verglichen. Diese Implementierung ist eigenständig und fokussiert geschützte Zugangsdaten, headless Betrieb und nachvollziehbare lokale Jobs; sie installiert und kopiert keinen Code aus jenem Projekt.

Primärquellen: [SANE-Geräteliste](https://www.sane-project.org/lists/sane-mfgs-cvs.html), [SANE-API](https://sane-project.gitlab.io/standard/1.02/api.html), [python-sane](https://github.com/python-pillow/Sane), [Paperless-API](https://docs.paperless-ngx.com/api/), [Raspberry Pi](https://www.raspberrypi.com/documentation/computers/configuration.html), [Flask](https://flask.palletsprojects.com/), [Waitress](https://docs.pylonsproject.org/projects/waitress/).
