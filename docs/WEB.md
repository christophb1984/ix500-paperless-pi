# Weboberfläche – Version 0.2.5

Die Oberfläche läuft auf dem Pi und ist auf Handy/Computer im selben Netz erreichbar. Kein Desktop, keine neue SD-Karte. Ein eigener Webdienst verwaltet Profile und reicht Scanstarts an den bestehenden Scandienst weiter. Nur der Scandienst öffnet USB; die Paperless-Warteschlange bleibt dieselbe.

## Bestehenden Pi aktualisieren

1. Im bestehenden Git-Checkout `git pull --ff-only` ausführen. Stammt die Installation bisher aus einer ZIP, auf dem Pi einen eigenen Update-Checkout anlegen:

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/christophb1984/ix500-paperless-pi.git ix500-paperless-pi-update
cd ix500-paperless-pi-update
```

2. Im Projektordner, während kein Scan läuft:

```bash
sudo bash update.sh
```

Das Update installiert `python3-sane`, `python3-flask`, `python3-waitress` und weitere Laufzeitpakete aus apt sowie die Projektdateien aus dem Checkout. Es verändert keine persönlichen Netzwerk-/SSH-Einstellungen und fragt Paperless-URL oder Token nicht erneut ab. Vorhandene Jobs und bisherige Scanwerte bleiben erhalten. Ein laufender oder wartender Scan verhindert das Update. Der Dienststopp erfolgt unter derselben Startsperre wie Hardwaretaste und Browser. Bei einer alten Version ohne Kontrollkanal den Dienst zuerst bewusst im Leerlauf stoppen. Während des Updates keine separaten Administrator-Scans oder Verwaltungsbefehle ausführen. Eine abgebrochene Upload-Anfrage bleibt zur manuellen Prüfung erhalten.

3. Ein separates **Webpasswort** mit mindestens zwölf Zeichen festlegen und wiederholen. Standardport `8080` mit Enter bestätigen. Das ist ein neues Passwort; SSH-Passwort und Paperless-Token bleiben unverändert. Bei wiederholtem Update kann das Webpasswort beibehalten werden.
4. Im Browser öffnen:

```text
http://HOSTNAME.local:8080/
```

Dabei `HOSTNAME` durch den eingerichteten Pi-Hostnamen ersetzen. Alternativ `http://PI-IP:8080/`. Der Hostname kann auf manchen Geräten nicht auflösbar sein; dann die Pi-IP aus dem Router verwenden. Eine benutzerdefinierte Portwahl entsprechend ersetzen.

HTTP ist für ein vertrauenswürdiges Heimnetz gedacht und verschlüsselt auch das Webpasswort nicht. Keine Portweiterleitung ins Internet einrichten. Für Zugriff von außerhalb ein vorhandenes VPN verwenden; bei Bedarf kann ein eigener HTTPS-Reverse-Proxy vorgeschaltet werden. Bei einem eigenen HTTPS-Reverse-Proxy muss `public_origin` in der geschützten `web.json` auf dessen exakte externe Basisadresse gesetzt und der Webdienst neu gestartet werden, damit Origin-Prüfung und Secure-Cookie passen. Die App aktiviert weder HTTPS noch Routerfreigaben automatisch.

## Bedienung

- **Scanprofil:** gespeichertes Profil laden; Auswahl allein ändert die blaue Taste noch nicht. „Für blaue Taste aktivieren“ übernimmt ein vorhandenes Profil. „Profil speichern & aktivieren“ speichert die angezeigten Änderungen unter dem eingegebenen Profilnamen und aktiviert es. Neuer Name = zusätzliche Profilkopie, maximal 30 Profile.
- **Scan starten:** Papier einlegen. Der Browser startet mit den aktuell angezeigten Werten, auch wenn diese noch nicht gespeichert sind. Eine zweite Anforderung während eines laufenden oder wartenden Auftrags wird abgelehnt.
- **Automatisch:** scannt physisch beide Seiten und entfernt danach anhand des Leerseitenfilters leere Seiten. Es gibt keine Erkennung vor dem Papierdurchlauf. Ist der Filter beim Auswählen ausgeschaltet, setzt die Oberfläche `0.1 %`; vorhandene aktive Filterwerte bleiben erhalten. Beide Filterparameter bleiben einstellbar, `0` ist in diesem Modus nicht zulässig. Bedruckte Rückseiten bleiben erhalten, eine kleine oder blasse Bedruckung kann bei ungeeigneten Werten trotzdem entfallen. Ein vollständiges Original-PDF bleibt bei entfernten Seiten auf dem Pi.
- **Hardwaretaste:** nutzt das gespeicherte aktive Profil. Änderungen wirken erst auf den nächsten Scan. Ein laufender Scan behält seine ursprünglichen Werte. Browserstart und Hardwaretaste steuern denselben Worker.
- **Papier & Qualität:** Automatisch, einseitig Vorder-/Rückseite oder Duplex, Farbe/Graustufen/Schwarzweiß, 100–600 dpi, A4/Legal/eigener fester Bereich, JPEG-Qualität 40–100. Das Backend kann die angebotenen Bereiche weiter begrenzen; nicht unterstützte Werte werden abgelehnt.
- **Bild & Leerseiten:** native Helligkeits-/Kontrast-/Gammafelder erscheinen, wenn das Backend sie liefert. „Anpassen“ zum Überschreiben aktivieren. Leerseitenfilter arbeitet auf den gescannten Bildern, vor PDF-Erzeugung; `0` deaktiviert ihn. Höherer Prozentwert entfernt mehr, kleinere Dunkelheitsschwelle ignoriert mehr helles Durchscheinen. Das Original-PDF bleibt bei entfernten Seiten erhalten.
- **Erweiterte Geräteoptionen:** native Titel, Erklärungen, Wertebereiche und Auswahlwerte vom tatsächlich angeschlossenen Gerät. Nach Modus-/Optionswechsel „Geräteoptionen aktualisieren“. Abhängige Werte können erst danach aktiv werden: etwa zunächst Gamma-Anpassung einschalten und aktualisieren, dann die Tabelle ändern. Zahlenvektoren verwenden JSON-Listen mit der angezeigten/erwarteten Zahl an Einträgen.
- **Zusatzoptionen zurücksetzen:** entfernt native Überschreibungen aus dem Entwurf, nützlich bei nicht mehr aktiven oder inkompatiblen Optionen. Danach aktualisieren und speichern.
- **Status:** Scannerzustand, freier Speicher, Upload-/Importzahlen und zurückgehaltene Jobs. Paperless-Tokens, Passwörter und Dokumentinhalte werden nicht an den Browser geschickt.

Nicht jede native Option ist ein Einstellwert: Nur-Lese-Sensoren und Geräteaktionen werden nur angezeigt. Pipelineeigene Quelle, Scanbereich, Backend-Leerseitenfilter und Batch-Steuerung sind nicht frei überschreibbar. Dafür existieren die eigenen Formfelder. So bleibt die Prüfung auf unvollständige Scans erhalten. Das ist keine generische Scanner-Fernwartung mit Zähler-Reset oder Shell-Zugang.

## Speicherung und Sicherheit

- Root-Konfiguration bleibt `/etc/ix500-paperless/config.json` mit Paperless-Zugangsdaten.
- Gespeicherte Profile: `/var/lib/ix500-paperless/control.json`. Beim ersten Speichern werden die bisherigen Scanwerte als Profilgrundlage übernommen. Danach sind die Webprofile maßgeblich; direkte Änderungen an Scanwerten der Root-Datei überschreiben gespeicherte Profile nicht.
- Webzugang: `/etc/ix500-paperless/web.json`, `root:ix500`, `0640`, Passwort-Hash (PBKDF2-SHA256) und zufälliger Sitzungsschlüssel. Kein Klartextpasswort. Root und Dienstkonto können die Dateien lesen.
- Anmeldung gilt zwölf Stunden, mit HttpOnly-/SameSite-Strict-Cookie und CSRF-Schutz für schreibende Anfragen. Zehn Anmeldeversuche in fünf Minuten je Client-IP; Zähler wird bei Dienstneustart zurückgesetzt. Keine externen Skripte, Schriftarten oder CDN-Abhängigkeiten.
- Der Webdienst läuft als `ix500`, ohne sudo und ohne USB-Zugriff. Er hat dieselbe lokale Vertrauensgrenze wie die Scan-Appliance, ist keine zusätzliche Isolation gegenüber einem kompromittierten Dienstkonto.
- Browser-Startaufträge enthalten eine Profilkopie, keine Zugangsdaten. Beim Neustart des Scandiensts werden alte wartende Startaufträge verworfen. Ein neu angenommener Auftrag verfällt nach 30 Sekunden ohne Übernahme. Gerät ausgeschaltet/belegt oder Worker nicht erreichbar: kein Scanstart.

## Passwort ändern / Diagnose

```bash
sudo python3 /opt/ix500-paperless/setup_web.py
sudo systemctl restart ix500-web.service
```

Bei „Webpasswort beibehalten?“ `nein` eingeben. Ein neues Passwort erneuert auch den Sitzungsschlüssel und meldet bestehende Browser ab.

```bash
sudo systemctl status ix500-web.service ix500-scan.service
sudo journalctl -u ix500-web.service -u ix500-scan.service -n 60 --no-pager
```

- **Seite nicht erreichbar:** tatsächliche Pi-IP/Port prüfen, Dienste aktiv, vorhandene Firewall auf dem Pi kontrollieren. Die Installation verändert keine Firewallregeln.
- **Scanner nicht bereit:** aufklappen, USB und Strom prüfen. Bei Profilfehlern Zusatzoptionen zurücksetzen, Basiswerte wählen und Geräteoptionen neu abfragen. Ein fremder Scanprozess darf USB nicht gleichzeitig belegen.
- **Option im Modus nicht verfügbar:** andere Werte können abhängen; aktualisieren. Eine alte gespeicherte Geräteoption kann nach einem Treiberwechsel unzulässig sein; zurücksetzen statt still ignorieren.
- **Scanstart angenommen, aber Papier läuft nicht:** Geräteprofil/Fehler prüfen; das Backend wird vor dem Transport erneut validiert. Root-Zugang/Journal zeigt die lokale Diagnose, die Warteschlange behält Teilscans.
- **Sitzung ungültig:** Seite neu laden und anmelden; nach Neustart/Passwortwechsel erwartbar.

## Abnahme am echten Pi

Softwaretests simulieren den Scanner. Die unterstützten Kombinationen und nativen Optionen sind nicht flächendeckend auf realer Hardware getestet. Nach dem Update testen:

1. Browser anmelden und sichtbare Geräteoptionen prüfen.
2. Einseitiges Profil speichern, ein einzelnes Blatt scannen: eine PDF-Seite, Upload erfolgreich.
3. Duplexprofil speichern, beidseitiges Blatt per Browser und danach per blauer Taste: je zwei Seiten.
4. Während eines Scans Werte ändern: laufender Job unverändert, nächste Tastenauslösung mit neuem Profil.
5. Kontrast/Helligkeit nur ändern, wenn als aktiv gemeldet. Leerseitenfilter mit Original vergleichen.
6. Automatisch mit einer bedruckten Vorderseite und leerer Rückseite testen: eine Seite im Ergebnis-PDF, zwei im Original. Danach ein beidseitig bedrucktes Blatt: beide Seiten im Ergebnis.
7. Pi neu starten: Dienste starten, Profile bleiben erhalten. Browser nach Bedarf neu anmelden.

Implementierung: [Flask](https://flask.palletsprojects.com/), [Waitress](https://docs.pylonsproject.org/projects/waitress/), native Optionsabfrage über [python-sane](https://github.com/python-pillow/Sane). Laufzeitpakete werden aus der Distribution installiert und nicht im Projektarchiv mitgeliefert.

## Browserprüfung für Entwickler (optional)

Zusätzlich zu den Unittests kann in einer isolierten Entwicklungsumgebung `pip install playwright` und `python -m playwright install chromium` ausgeführt werden. Danach `python tests/browser_smoke.py`. Die Prüfung startet ausschließlich eine lokale Waitress-Instanz mit simulierten Optionen, prüft den Benutzerablauf und schreibt Screenshots unter `work/`. Kein physischer Scanner oder echter Paperless-Server wird verwendet. Diese zusätzlichen Testabhängigkeiten werden nicht auf dem Pi installiert.
