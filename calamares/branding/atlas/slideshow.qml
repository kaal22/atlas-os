import QtQuick 2.15

Rectangle {
    id: root
    color: "#0b0f14"
    anchors.fill: parent

    Image {
        id: mark
        // Prefer the wide glowing triangle art for the slideshow pane
        source: "triangle-glow-master.png"
        width: parent.width * 0.72
        height: parent.height * 0.55
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: parent.height * 0.08
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        opacity: 1.0
        // If master art is missing, fall back to logo.png
        onStatusChanged: {
            if (status === Image.Error)
                source = "logo.png"
        }
    }

    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: mark.bottom
        anchors.topMargin: 20
        spacing: 10
        width: parent.width * 0.8

        Text {
            text: "Atlas OS"
            color: "#ffffff"
            font.pixelSize: 34
            font.bold: true
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Text {
            text: "Private offline AI and knowledge environment"
            color: "#a8b2c1"
            font.pixelSize: 15
            wrapMode: Text.WordWrap
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
