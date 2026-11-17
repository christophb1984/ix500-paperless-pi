# Optionaler Image-Build

Der Installer ist der primäre und einfacher prüfbare Weg. Ein komplettes `.img` wird in diesem Projekt nicht ausgeliefert. Der folgende Ansatz ist dokumentiert, **nicht hier gebaut oder gebootet**. Ein öffentlicher Basis-Build darf keine persönlichen Zugangsdaten enthalten; eine private vollständig vorkonfigurierte SD-Karte ist anschließend ein Geheimnisträger.

## Empfohlener Weg

Offizielles Raspberry Pi OS Lite 64-bit mit Pi Imager personalisieren → starten → `sudo ./install.sh`. So werden Netzwerk, Benutzer und SSH schon beim Flashen eingerichtet. Danach erfasst der Assistent Paperless-Zugang und Scanprofil.

Für wiederholte Gerätebereitstellung kann ein eigenes Basis-Image Pakete/Projektdateien vorinstallieren. Der vorhandene Modus `sudo ./install.sh --prepare-image` führt ausschließlich diese Vorbereitung aus: keine Fragen, kein API-Token, keine Aktivierung der Scandienste. Zum Abschluss am gebooteten Gerät:

```bash
sudo python3 /opt/ix500-paperless/setup_wizard.py
sudo python3 /opt/ix500-paperless/setup_web.py
sudo systemctl enable --now ix500-web.service
```

Es gibt keinen ungesicherten Web-Assistenten und keinen öffentlichen Standard-SSH-Zugang.

## pi-gen-Integration als Build-Rezept

[pi-gen](https://github.com/RPi-Distro/pi-gen) ist das Raspberry-Pi-OS-Buildwerkzeug. Für 64-bit dessen `arm64`-Branch verwenden und einen geprüften Commit festhalten. Build auf einem passenden Linux-System nach dessen Anleitung, nicht direkt in macOS ausführen. Upstream kann seine Stages/Erstbenutzereinrichtung verändern; deren dokumentierte Optionen für den verwendeten Commit sind maßgeblich.

1. pi-gen und dieses Projekt nebeneinander in Pfaden ohne Leerzeichen auschecken. Für eine releasefähige Reproduktion beide Commit-IDs, OS-Release und Paketversionen festhalten.
2. Eine Lite-Buildkonfiguration für Bookworm/Trixie nach der pi-gen-Anleitung erstellen, nur Lite-Stages verwenden. Keine WLAN-PSK, API-Tokens, privaten SSH-Schlüssel oder Administrator-Passwörter in das veröffentlichte Build-Repository schreiben.
3. Am Ende der Lite-Stage einen zusätzlichen Unterordner anlegen, Projektdateien ins Rootfs kopieren und im chroot den Installer mit `--prepare-image` ausführen. Beispiel für einen eigenen `00-run.sh`-Hook (die Projektkopie liegt in `files/ix500-paperless-pi` des Unterordners):

```bash
#!/bin/bash
set -e
install -d "${ROOTFS_DIR}/tmp/ix500-project"
cp -a files/ix500-paperless-pi/. "${ROOTFS_DIR}/tmp/ix500-project/"
on_chroot <<'CHROOT'
cd /tmp/ix500-project
bash ./install.sh --prepare-image
rm -rf /tmp/ix500-project
CHROOT
```

4. Die eigene Stage so in die Lite-Exportfolge einfügen, dass sie vor dem Image-Export ausgeführt wird. Die aktuelle Stage-/Exportstruktur des gepinnten pi-gen-Commits prüfen, keine universelle Stage-Liste unterstellen.
5. Als OS-Metadaten eindeutig ein eigenes Projekt benennen. Eigene Netzwerk-/Benutzerkonfiguration erst im privaten Provisionierungsschritt anwenden. Bei generischen Custom-Images ist Imager-Personalisierung **nicht automatisch garantiert**: Erstbenutzer-/SSH-/WLAN-Provisionierung am konkreten Image testen; andernfalls lokale Konsole verwenden.
6. Das gebaute Image zunächst auf beiden Zielmodellen booten und die vollständige [Abnahme](ACCEPTANCE.md) durchführen. Prüfen, dass `/etc/ix500-paperless/config.json` fehlt, die Scandienste deaktiviert sind und keine persönlichen Netzwerkprofile/SSH-Schlüssel enthalten sind.
7. Für Veröffentlichung Checksummen und Buildinformationen bereitstellen. Lizenzinformationen und erforderliche Quellcodeangebote sämtlicher OS-Pakete beachten. Keine SD-Karte klonen, auf der bereits produktiv gescannt oder persönliche Konfiguration gespeichert wurde.

## „Nur flashen, dann läuft alles“

Das ist für eine **private** vorbereitete Karte möglich, nachdem Benutzer/Netzwerk/SSH und Paperless-Zugang eingetragen und die Hardware geprüft wurden. Das resultierende Image enthält Geheimnisse und Dokumentzugriff; nicht öffentlich hochladen. Für ein öffentliches Image braucht es einmalige individuelle Provisionierung. Dieses Projekt setzt dafür auf Imager plus interaktiven SSH-/Konsolenassistenten, statt ungeprüfte Boot-Magie oder universelle Standardzugänge zu versprechen.
