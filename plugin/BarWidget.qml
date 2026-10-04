pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Strings.js" as Strings

// Bar entry for Omarchy Lab: a flask icon that opens a small panel to start a
// test in a terminal, open results, share them, or stop a running test.
// Nothing runs until the user picks an action.
Panel {
  id: root
  moduleName: "io.github.charlie0113-t.omarchy-lab"
  ipcTarget: moduleName

  readonly property string pluginDir: decodeURIComponent(
    Qt.resolvedUrl("..").toString().replace(/^file:\/\//, "").replace(/\/$/, ""))
  readonly property string actionScript: pluginDir + "/plugin/action.sh"
  readonly property string language: Strings.language(Qt.locale().name)
  readonly property color foreground: root.barForeground
  readonly property string fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
  property bool testRunning: false
  property int cursor: -1

  readonly property var runActions: [
    { id: "typical", icon: "", label: tr("typical"), tip: tr("typicalTip") },
    { id: "daily", icon: "", label: tr("daily"), tip: tr("dailyTip") },
    { id: "agent", icon: "", label: tr("agent"), tip: tr("agentTip") },
    { id: "agent-live", icon: "", label: tr("agentLive"), tip: tr("agentLiveTip") }
  ]
  readonly property var resultActions: [
    { id: "open-report", icon: "", label: tr("openReport"), tip: "" },
    { id: "open-folder", icon: "", label: tr("openFolder"), tip: "" },
    { id: "share", icon: "", label: tr("share"), tip: tr("shareTip") }
  ]
  readonly property var stopActions: testRunning ? [{ id: "stop", icon: "", label: tr("stop"), tip: tr("stopTip") }] : []
  readonly property var allActions: runActions.concat(resultActions, stopActions)

  function tr(key) { return Strings.text(language, key) }

  function run(actionId) {
    Quickshell.execDetached(["bash", actionScript, actionId, language])
    if (actionId === "stop") {
      testRunning = false
      return
    }
    close()
  }

  function moveCursor(delta) {
    var count = allActions.length
    cursor = cursor < 0 ? (delta > 0 ? 0 : count - 1) : (cursor + delta + count) % count
  }

  function refreshStatus() {
    if (!statusProc.running) statusProc.running = true
  }

  onOpenedChanged: {
    cursor = -1
    if (opened) refreshStatus()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: statusProc
    command: ["bash", root.actionScript, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.testRunning = text.trim() === "running"
    }
  }

  // Only polls while the panel is open; the widget is idle otherwise.
  Timer { interval: 2000; running: root.opened; repeat: true; onTriggered: root.refreshStatus() }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: ""
    active: root.testRunning
    tooltipText: root.tr("title")
    onPressed: function(b) { root.toggle() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) { root.moveCursor(dy !== 0 ? dy : dx) }
      onActivateRequested: if (root.cursor >= 0) root.run(root.allActions[root.cursor].id)
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(10)

        Row {
          spacing: Style.space(12)

          Text {
            textFormat: Text.PlainText
            text: ""
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.display
            anchors.verticalCenter: parent.verticalCenter
          }

          Column {
            spacing: Style.space(2)
            anchors.verticalCenter: parent.verticalCenter

            Text {
              textFormat: Text.PlainText
              text: root.tr("title")
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }

            Text {
              textFormat: Text.PlainText
              text: (root.testRunning ? root.tr("running") : root.tr("ready")).toUpperCase()
              color: root.testRunning && root.bar ? root.bar.urgent : Qt.darker(root.foreground, 1.4)
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
            }
          }
        }

        PanelSeparator { foreground: root.foreground }

        PanelSectionHeader {
          text: root.tr("runHeader")
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Repeater {
          model: root.runActions
          ActionRow { offset: 0 }
        }

        PanelSeparator { foreground: root.foreground }

        PanelSectionHeader {
          text: root.tr("resultsHeader")
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Repeater {
          model: root.resultActions
          ActionRow { offset: root.runActions.length }
        }

        Repeater {
          model: root.stopActions
          ActionRow {
            offset: root.runActions.length + root.resultActions.length
            foreground: root.bar ? root.bar.urgent : Color.urgent
          }
        }
      }
    }
  }

  component ActionRow: Button {
    required property var modelData
    required property int index
    property int offset: 0

    width: column.width
    leftAlign: true
    iconText: modelData.icon
    text: modelData.label
    tooltipText: modelData.tip
    foreground: root.foreground
    fontFamily: root.fontFamily
    fontSize: Style.font.bodySmall
    hasCursor: root.cursor === offset + index
    onClicked: root.run(modelData.id)
    onHovered: function(isHovered) { if (isHovered) root.cursor = offset + index }
  }
}
