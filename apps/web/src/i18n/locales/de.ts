// SPDX-License-Identifier: Apache-2.0
// German (de) message catalog — first shipped non-English locale.
// Pending native-speaker review before release.

import type { LocaleMessages } from './en'

export const de: LocaleMessages = {
  errors: {
    schemaValidation: 'Die Anfrage enthielt ungültige Daten.',
    packNotFound: 'Das angeforderte Paket wurde nicht gefunden.',
    scenarioNotFound: 'Das angeforderte Szenario wurde nicht gefunden.',
    sessionNotFound: 'Sitzung nicht gefunden.',
    modelNotLoaded:
      'Kein KI-Modell geladen. Öffnen Sie die Einstellungen, um ein Modell zu installieren.',
    runtimeUnavailable:
      'Die lokale Laufzeitumgebung ist nicht verfügbar. Prüfen Sie die Protokolle.',
    safetyViolation: 'Der Inhalt wurde durch die Sicherheitsrichtlinie blockiert.',
    turnLimitExceeded: 'Das Zuglimit für dieses Szenario wurde erreicht.',
    turnTimeout: 'Der Zug hat das Zeitlimit überschritten. Bitte versuchen Sie es erneut.',
    internalError: 'Ein interner Fehler ist aufgetreten.',
    unauthorized: 'Nicht autorisiert.',
    unknown: 'Ein unerwarteter Fehler ist aufgetreten.',
  },
  error: {
    heading: 'Etwas ist schiefgelaufen',
    subheading: 'In der App ist ein unerwarteter Fehler aufgetreten.',
    details: 'Fehlerdetails',
    tryAgain: 'Erneut versuchen',
    goHome: 'Zur Startseite',
    reportIssue: 'Problem melden',
    documentation: 'Dokumentation',
    logsLabel: 'Protokolle:',
  },
  nav: {
    appTitle: 'Gesprächssimulator',
    skipToMain: 'Zum Hauptinhalt springen',
    mainNavigation: 'Hauptnavigation',
    home: 'Startseite',
    scenarios: 'Szenarien',
    logbook: 'Logbuch',
    workbench: 'Werkbank',
    settings: 'Einstellungen',
    support: 'Support',
  },
  home: {
    title: 'Gesprächssimulator',
    tagline:
      'Üben Sie Vorstellungsgespräche, Verhandlungen, Sprachen und schwierige Gespräche.',
    primaryActions: 'Hauptaktionen',
    yourTraining: 'Ihr Training',
    training: {
      loading: 'Wird geladen…',
      empty: 'Noch keine Sitzungen.',
      emptyCta: 'Schließen Sie Ihr erstes Szenario ab, um Ihren Fortschritt zu verfolgen.',
      startNow: 'Jetzt starten →',
      sessions: 'Sitzungen',
      streak: 'Serie',
      day: 'Tag',
      days: 'Tage',
      strongest: 'Stärkste',
      needsWork: 'Verbesserungsbedarf',
      lastSession: 'Letzte Sitzung',
      viewFull: 'Vollständiges Logbuch anzeigen →',
    },
    readinessSection: 'Systembereitschaft',
    getStartedSection: 'Ohne Modell loslegen',
    helpSection: 'Hilfe und Ressourcen',
    startScenario: 'Szenario starten',
    createEdit: 'Szenario erstellen / bearbeiten',
    installModel: 'Modell installieren',
    importPack: 'Paket importieren',
    creatorWorkbenchGuide: 'Anleitung für die Erstellerwerkbank',
    readDocs: 'Dokumentation lesen',
    status: {
      heading: 'Status',
      localRuntime: 'Lokale Laufzeitumgebung',
      llm: 'LLM',
      stt: 'STT',
      tts: 'TTS',
      networkRequired: 'Netzwerk zum Spielen erforderlich',
      packs: 'Pakete',
      checking: 'Überprüfe…',
      ready: 'Bereit',
      unavailable: 'Nicht verfügbar',
      notInstalled: 'Nicht installiert',
      yes: 'Ja',
      no: 'Nein',
      noneInstalled: 'Keine installiert',
      packsInstalledCount: '{{count}} installiert',
    },
    unreachable: {
      title: 'Die Konversations-Engine antwortet nicht',
      message:
        'Die App kann die Konversations-Engine gerade nicht erreichen. Versuchen Sie einen Neustart oder sehen Sie in der Fehlerbehebungsanleitung nach.',
      restart: 'App neu starten',
      openSupport: 'Support-Paket erstellen',
      troubleshootingDocs: 'Fehlerbehebungsdokumentation',
      reportIssue: 'Problem melden',
    },
    portConflict: {
      title: 'Eine andere App belegt einen erforderlichen Port',
      message:
        'Schließen Sie die konfliktverursachende App und starten Sie den Gesprächssimulator neu. Port 7355 muss frei sein.',
      details: 'Details: {{error}}',
      portTroubleshooting: 'Port-Konflikt-Anleitung',
      reportIssue: 'Problem melden',
    },
    lastError: {
      message: 'Letzter Fehler: {{error}}',
      reportIssue: 'Problem melden',
    },
    recovery: {
      restartEngine: 'Konversations-Engine neu starten',
      restarting: 'Startet neu…',
      openSupport: 'Support-Paket erstellen',
      troubleshootingDocs: 'Fehlerbehebungsdokumentation',
    },
    noModel: {
      heading: 'Kein Modell konfiguriert',
      description:
        'Wählen Sie, wie Sie beginnen möchten. Sie können dies jederzeit in den Einstellungen ändern.',
      gguf: {
        title: 'GGUF-Modell installieren',
        description:
          'Laden Sie eine lokale Modelldatei herunter. Nach dem ersten Download funktioniert es offline.',
        action: 'GGUF-Modell installieren →',
      },
      ollama: {
        title: 'Ollama verbinden',
        description:
          'Verwenden Sie eine vorhandene Ollama-Installation. Kein zusätzlicher Download erforderlich.',
        action: 'Ollama verbinden →',
      },
      demo: {
        title: 'Textnur-Demo ausprobieren',
        description:
          'Erkunden Sie die Benutzeroberfläche jetzt mit skriptierten NPC-Antworten – kein Modell erforderlich. Die Antwortqualität ist im Vergleich zu einem echten KI-Modell begrenzt.',
        action: 'Textnur-Demo ausprobieren →',
      },
    },
    missingPack: {
      title: 'Keine Szenarienpakete installiert',
      description:
        'Ihr Modell ist bereit, aber es gibt keine Pakete zum Spielen. Offizielle Pakete wiederherstellen, ein Paket importieren oder die Bibliothek durchsuchen.',
      restoreAction: 'Offizielle Pakete wiederherstellen',
      restoring: 'Wird wiederhergestellt…',
      restoreDone: 'Offizielle Pakete wiederhergestellt ✓',
      action: 'Zur Bibliothek →',
    },
    help: {
      heading: 'Hilfe',
      documentation: 'Dokumentation',
      reportIssue: 'Problem melden',
      logsFolder: 'Protokollordner:',
      logsPath: '~/.convsim/logs',
      logsContext: '(genauen Pfad im Bereich „Lokale Ordner" sehen)',
      dataFolder: 'Datenordner:',
      dataPath: '~/.convsim',
      dataContext: '(genauen Pfad im Bereich „Lokale Ordner" sehen)',
    },
  },
  settings: {
    title: 'Einstellungen',
    localFirst: {
      ariaLabel: 'Hinweis: nur lokal',
      label: 'Lokal-zuerst.',
      description:
        'Gespräche werden vollständig auf Ihrem Gerät verarbeitet. Es werden keine Telemetriedaten gesammelt, keine Transkripte automatisch hochgeladen und kein Modell oder Paket ohne explizite Aktion von Ihnen heruntergeladen.',
    },
    transcript: {
      heading: 'Transkript',
      saveLabel: 'Transkripte lokal speichern',
      saveOn:
        'Gesprächstranskripte werden nur in Ihrem lokalen Datenordner gespeichert – niemals hochgeladen.',
      saveOff:
        'Transkripte werden nicht gespeichert. Das Gespräch dieser Sitzung kann nach Beendigung weder exportiert noch durchsucht werden.',
      notSavedWarning:
        'Nicht gespeichert – das Transkript geht verloren, wenn diese Sitzung endet.',
    },
    runtime: {
      heading: 'Laufzeitumgebung',
      description:
        'Wählen Sie den aktiven KI-Anbieter und das Modell. Erweiterte Einstellungen sind standardmäßig ausgeblendet.',
      openModelManagerLink: 'Modellverwaltung öffnen →',
      openModelManagerLabel: 'Modellverwaltung öffnen',
    },
    voice: {
      heading: 'Sprachausgabe',
      cacheLabel: 'TTS-Audio lokal zwischenspeichern',
      cacheDescription:
        'Das Zwischenspeichern generierter Sprache beschleunigt wiederholte Sätze. Zwischengespeichertes Audio bleibt auf Ihrem Gerät und wird niemals geteilt.',
    },
    steamCloud: {
      heading: 'Steam-Cloud-Synchronisierung',
      active: 'Steam Cloud ist für diese Sitzung aktiv.',
      description:
        'Beim Start über Steam wird eine kleine Datei zwischen Ihren Geräten synchronisiert, damit Ihre Einstellungen automatisch übernommen werden. Alle Konversationsdaten verbleiben ausschließlich auf dem jeweiligen Gerät.',
      syncedHeading: 'Was Steam Cloud synchronisiert:',
      syncedModel: 'Zuletzt verwendete Modellauswahl',
      excludedHeading: 'Was ausschließlich auf diesem Gerät bleibt:',
      excludedTranscripts: 'Konversationstranskripte und Sitzungsverlauf',
      excludedPrompts: 'Prompts und Szenario-Antworten',
      excludedAudio: 'Rohe Audioaufnahmen',
      excludedModels: 'Heruntergeladene KI-Modelldateien',
      excludedCrashLogs: 'Absturzberichte und Diagnoseprotokolle',
      excludedPacks: 'Importierte private Szenario-Pakete',
    },
    packs: {
      heading: 'Paketverwaltung',
      description:
        'Pakete fügen Ihrer Bibliothek Szenarien hinzu. Importieren Sie eine Paket-ZIP-Datei – kein ausführbarer Inhalt wird akzeptiert. Pakete werden beim Import validiert und nur auf diesem Gerät gespeichert.',
      importFileLabel: 'Paket-ZIP-Datei auswählen',
      importButton: 'Paket importieren (.zip)',
      importing: 'Importiere…',
      importedSuccess: '„{{name}}" importiert',
      importError: 'Import fehlgeschlagen.',
      loadError: 'Installierte Pakete konnten nicht geladen werden.',
      noPacks: 'Noch keine Pakete installiert.',
      scenarioCount_one: '{{count}} Szenario',
      scenarioCount_other: '{{count}} Szenarien',
    },
    folders: {
      heading: 'Lokale Ordner',
      description:
        'Alle Daten bleiben auf diesem Gerät. Nutzen Sie diese Pfade zur manuellen Überprüfung oder Sicherung.',
      loadError: 'Ordnerpfade konnten nicht abgerufen werden.',
      loading: 'Lade…',
      data: 'Daten',
      logs: 'Protokolle',
      models: 'Modelle',
      packs: 'Pakete',
      exports: 'Exporte',
      cache: 'Cache',
      crash_bundles: 'Absturzberichte',
      copy: 'Kopieren',
      copied: 'Kopiert!',
      open: 'Öffnen',
      copyLabel: 'Pfad des Ordners „{{folder}}" kopieren',
      openLabel: 'Ordner „{{folder}}" öffnen',
      openError:
        'Der Ordner konnte nicht automatisch geöffnet werden. Kopieren Sie den Pfad und öffnen Sie ihn manuell.',
    },
    clearData: {
      heading: 'Lokale Daten löschen',
      description:
        'Löscht dauerhaft alle Sitzungen, Transkripte und zwischengespeicherten Daten von Ihrem Gerät. Installierte Modelle werden nicht entfernt.',
      confirmMessage:
        'Dadurch werden alle Sitzungen und Transkripte dauerhaft von diesem Gerät gelöscht. Dieser Vorgang kann nicht rückgängig gemacht werden.',
      done_one: '1 Sitzung gelöscht.',
      done_other: '{{count}} Sitzungen gelöscht.',
      doneLocal: 'Lokale Daten wurden gelöscht.',
      error: 'Daten konnten nicht gelöscht werden. Bitte versuchen Sie es erneut.',
      unknownError: 'Unbekannter Fehler.',
      clearing: 'Lösche…',
      confirm: 'Bestätigen – alles löschen',
      clear: 'Alle lokalen Daten löschen',
      cancel: 'Abbrechen',
    },
    sessions: {
      heading: 'Ihre Sitzungen',
      description: 'Sitzung als JSON exportieren oder dauerhaft löschen.',
      loadError: 'Sitzungen konnten nicht geladen werden.',
      deleteError: 'Sitzung konnte nicht gelöscht werden.',
      exportError: 'Sitzung konnte nicht exportiert werden.',
      loading: 'Lade…',
      noSessions: 'Noch keine Sitzungen.',
      export: 'Exportieren',
      exportLabel: 'Sitzung {{id}} exportieren',
      delete: 'Löschen',
      deleteLabel: 'Sitzung {{id}} löschen',
      confirmDelete: 'Löschen bestätigen',
      confirmDeleteLabel: 'Löschen von Sitzung {{id}} bestätigen',
      cancelDelete: 'Abbrechen',
      cancelDeleteLabel: 'Löschen von Sitzung {{id}} abbrechen',
    },
    advanced: {
      showAdvanced: 'Erweitert anzeigen',
      hideAdvanced: 'Erweitert ausblenden',
      heading: 'Erweitert',
      rawAudioLabel: 'Rohe Audioaufnahmen speichern (erweitert)',
      rawAudioDescription:
        'Standardmäßig deaktiviert. Wenn aktiviert, werden unverarbeitete Mikrofonaufnahmen für die Fehlersuche bei der Spracheingabe in Ihrem Datenordner gespeichert. Nur aktivieren, wenn Sie STT-Genauigkeitsprobleme diagnostizieren.',
      rawAudioWarning:
        'Rohe Audio-Speicherung ist aktiv. Aufnahmen werden lokal gespeichert, bis Sie die lokalen Daten löschen.',
      devModeLabel: 'Entwickler-Debug-Modus',
      devModeDescription:
        'Zeigt ein Debug-Fenster im Gesprächsbildschirm mit rohen Modellausgaben, Zustandsänderungen, Ereignisauswertungen und versteckten NPC-Feldern. Für Entwickler, die Modelldrift oder Szenarioverhalten diagnostizieren. Laden Sie den Gesprächsbildschirm nach dem Umschalten neu.',
      devModeWarning:
        'Entwickler-Debug-Fenster ist aktiv. Interne Modelldaten sind im Gesprächsbildschirm sichtbar. Vor dem Teilen des Bildschirms deaktivieren.',
    },
    language: {
      heading: 'Sprache',
      description: 'Wählen Sie die Sprache der Benutzeroberfläche.',
      label: 'Oberflächensprache',
    },
  },
  debrief: {
    title: 'Sitzungsnachbesprechung',
    sessionLabel: 'Sitzung:',
    backToLibrary: '← Zurück zur Bibliothek',
    generating: 'Nachbesprechung wird erstellt…',
    error: {
      prefix: 'Nachbesprechung konnte nicht erstellt werden:',
      tryAgain: 'Erneut versuchen',
      transcriptOnly: 'Nur Transkript anzeigen',
    },
    fallback:
      'Nachbesprechung aus einer Vorlage erstellt – installieren Sie ein lokales Modell für detailliertes Feedback.',
    transcriptDisabled:
      'Das Transkript wurde für diese Sitzung deaktiviert. Zugdetails sind nicht verfügbar.',
    scenario: 'Szenario:',
    turns: 'Züge:',
    summary: 'Zusammenfassung',
    scorecard: 'Scorecard',
    strengths: 'Stärken',
    improvements: 'Verbesserungsbereiche',
    missedOpportunities: 'Verpasste Gelegenheiten',
    keyMoments: 'Schlüsselmomente',
    tryNextTime: 'Beim nächsten Mal versuchen',
    transcript: {
      heading: 'Transkript',
      noSaved: 'Für diese Sitzung wurde kein Transkript gespeichert.',
      ariaLabel: 'Gesprächstranskript',
      transcriptOnlyNotice:
        'Nachbesprechungserstellung fehlgeschlagen. Zeige nur Transkript.',
      turn: 'Zug {{number}}',
      you: 'Sie',
      npc: 'NPC',
      goToTurn: 'Zu Zug {{number}} gehen',
    },
    debugJson: 'Vollständiges Nachbesprechungs-JSON (Debug)',
    latency: 'Nachbesprechungserstellung: {{ms}} ms',
    score: {
      overall: 'Gesamtpunktzahl: {{score}} von 100 — {{grade}}',
      dimension: '{{label}}: {{score}} von 100',
      gradeGood: 'Gut',
      gradeFair: 'Befriedigend',
      gradeNeedsImprovement: 'Verbesserungswürdig',
    },
    keyMoment: {
      impact: 'Auswirkung: {{impact}}',
    },
    chart: {
      ariaLabel: '{{variable}} über die Züge',
    },
    outcomeBadge: {
      ariaLabel: 'Ergebnis: {{outcome}}',
    },
    actions: {
      replayVariation: 'Variation wiederholen',
      replaySameSetup: 'Gleiche Einrichtung wiederholen',
      starting: 'Starte…',
      retryDebrief: 'Nachbesprechung erneut versuchen',
      exportJSON: 'Sitzung als JSON exportieren',
      exporting: 'Exportiere…',
      exportMarkdown: 'Transkript exportieren (Markdown)',
      tryAnother: 'Anderes Szenario versuchen',
      privacyNotice:
        'Exportierte Dateien werden in Ihrem lokalen Download-Ordner gespeichert und verlassen Ihr Gerät nicht.',
    },
  },
}
