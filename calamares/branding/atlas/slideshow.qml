import QtQuick 2.15

Rectangle {
    id: root
    color: "#000000"
    anchors.fill: parent

    Image {
        id: mark
        source: "logo.png"
        width: Math.min(parent.width, parent.height) * 0.28
        height: width
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -36
        fillMode: Image.PreserveAspectFit
        smooth: true
        opacity: 0.95
    }

    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: mark.bottom
        anchors.topMargin: 28
        spacing: 10
        width: parent.width * 0.75

        Text {
            text: "Atlas OS"
            color: "#ffffff"
            font.pixelSize: 36
            font.bold: true
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Text {
            text: "Private offline AI and knowledge environment"
            color: "#a0a0a0"
            font.pixelSize: 16
            wrapMode: Text.WordWrap
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
