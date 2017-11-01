#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#######################################################################
#
# VidCutter - media cutter & joiner
#
# copyright © 2017 Pete Alexandrou
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#######################################################################

import logging
import math
import sys

from PyQt5.QtCore import QEvent, QObject, QRect, QSize, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QKeyEvent, QMouseEvent, QPaintEvent, QPainter, QPen, QTransform, QWheelEvent
from PyQt5.QtWidgets import (qApp, QGraphicsEffect, QHBoxLayout, QLabel, QLayout, QSizePolicy, QSlider, QStackedLayout,
                             QStackedWidget, QStyle, QStyleOptionSlider, QStylePainter, QWidget)

from vidcutter.libs.videoservice import VideoService


class VideoSlider(QSlider):
    def __init__(self, parent=None):
        super(VideoSlider, self).__init__(parent)
        self.parent = parent
        self.logger = logging.getLogger(__name__)
        self.theme = self.parent.theme
        self._styles = '''
        QSlider:horizontal {{
            margin: 16px 8px 32px;
            height: {sliderHeight}px;
        }}
        QSlider::sub-page:horizontal {{
            border: none;
            background: {subpageBgColor};
            height: {subpageHeight}px;
            position: absolute;
            left: 0;
            right: 0;
            margin: 0;
            margin-left: {subpageLeftMargin}px;
        }}
        QSlider::add-page:horizontal {{
            border: none;
            background: transparent;
        }}
        QSlider::handle:horizontal {{
            border: none;
            border-radius: 0;
            background: transparent url(:images/{handleImage}) no-repeat top center;
            width: 15px;
            height: {handleHeight}px;
            margin: -12px -8px -20px;
        }}
        QSlider::handle:horizontal:hover {{
            background: transparent url(:images/{handleImageSelected}) no-repeat top center;
        }}'''
        self._regions = list()
        self._regionHeight = 32
        self._regionSelected = -1
        self._cutStarted = False
        self.showThumbs = True
        self.thumbnailsOn = False
        self.offset = 8
        self.setOrientation(Qt.Horizontal)
        self.setObjectName('videoslider')
        self.setCursor(Qt.PointingHandCursor)
        self.setStatusTip('Set clip start and end points')
        self.setFocusPolicy(Qt.StrongFocus)
        self.setRange(0, 0)
        self.setSingleStep(1)
        self.setTickInterval(100000)
        self.setTracking(True)
        self.setTickPosition(QSlider.TicksBelow)
        self.setFocus()
        self.restrictValue = 0
        self.valueChanged.connect(self.restrictMove)
        self.rangeChanged.connect(self.on_rangeChanged)
        self.installEventFilter(self)

    def initStyle(self) -> None:
        bground = 'rgba(200, 213, 236, 0.85)' if self._cutStarted else 'transparent'
        height = 60
        handle = 'handle.png'
        handleSelect = 'handle-select.png'
        handleHeight = 85
        margin = 0
        timeline = ''
        self._regionHeight = 32
        if not self.thumbnailsOn:
            if self.parent.thumbnailsButton.isChecked():
                timeline = 'background: #000 url(:images/filmstrip.png) repeat-x left;'
            else:
                timeline = 'background: #000 url(:images/filmstrip-nothumbs.png) repeat-x left;'
                handleHeight = 42
                height = 15
                handle = 'handle-nothumbs.png'
                handleSelect = 'handle-nothumbs-select.png'
                self._regionHeight = 12
            self._styles += '''
            QSlider::groove:horizontal {{
                border: 1px ridge #444;
                height: {sliderHeight}px;
                margin: 0;
                {timelineBackground}
            }}'''
        else:
            self._styles += '''
            QSlider::groove:horizontal {{
                border: none;
                height: {sliderHeight}px;
                margin: 0;
            }}'''
        if self._cutStarted:
            handle = handleSelect
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            control = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)
            margin = control.x()
        self.setStyleSheet(self._styles.format(
            sliderHeight=height,
            subpageBgColor=bground,
            subpageHeight=height + 2,
            subpageLeftMargin=margin,
            handleImage=handle,
            handleImageSelected=handleSelect,
            handleHeight=handleHeight,
            timelineBackground=timeline))

    def setRestrictValue(self, value: int, force: bool = False) -> None:
        self.restrictValue = value
        if value > 0 or force:
            self._cutStarted = True
        else:
            self._cutStarted = False
        self.initStyle()

    @pyqtSlot(int)
    def restrictMove(self, value: int) -> None:
        if value < self.restrictValue:
            self.setSliderPosition(self.restrictValue)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QStylePainter(self)
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        if self.tickPosition() != QSlider.NoTicks:
            x = 8
            for i in range(self.minimum(), self.width(), 8):
                if i % 5 == 0:
                    h, w, z = 18, 1, 13
                else:
                    h, w, z = 8, 1, 23
                tickcolor = QColor('#8F8F8F' if self.theme == 'dark' else '#444')
                pen = QPen(tickcolor)
                pen.setWidthF(w)
                painter.setPen(pen)
                if self.tickPosition() in (QSlider.TicksBothSides, QSlider.TicksAbove):
                    y = self.rect().top() + z
                    painter.drawLine(x, y, x, y + h)
                if self.tickPosition() in (QSlider.TicksBothSides, QSlider.TicksBelow):
                    y = self.rect().bottom() - z
                    painter.drawLine(x, y, x, y - h)
                    if self.parent.mediaAvailable and i % 10 == 0 and (x + 4 + 50) < self.width():
                        painter.setPen(Qt.white if self.theme == 'dark' else Qt.black)
                        timecode = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), x - self.offset,
                                                                  self.width() - (self.offset * 2))
                        timecode = self.parent.delta2QTime(timecode).toString(self.parent.runtimeformat)
                        painter.drawText(x + 4, y + 6, timecode)
                if x + 30 > self.width():
                    break
                x += 15
        opt.subControls = QStyle.SC_SliderGroove
        painter.drawComplexControl(QStyle.CC_Slider, opt)
        for rect in self._regions:
            rect.setY(int((self.height() - self._regionHeight) / 2) - 8)
            rect.setHeight(self._regionHeight)
            brushcolor = QColor(150, 190, 78, 200) if self._regions.index(rect) == self._regionSelected \
                else QColor(237, 242, 255, 200)
            painter.setBrush(brushcolor)
            painter.setPen(QColor(50, 50, 50, 170))
            painter.drawRect(rect)
        opt.activeSubControls = opt.subControls = QStyle.SC_SliderHandle
        painter.drawComplexControl(QStyle.CC_Slider, opt)

    def addRegion(self, start: int, end: int) -> None:
        x = self.style().sliderPositionFromValue(self.minimum(), self.maximum(), start - self.offset,
                                                 self.width() - (self.offset * 2))
        y = int((self.height() - self._regionHeight) / 2)
        width = self.style().sliderPositionFromValue(self.minimum(), self.maximum(), end - self.offset,
                                                     self.width() - (self.offset * 2)) - x
        height = self._regionHeight
        self._regions.append(QRect(x + self.offset, y - 8, width, height))
        self.update()

    def switchRegions(self, index1: int, index2: int) -> None:
        reg = self._regions.pop(index1)
        self._regions.insert(index2, reg)
        self.update()

    def selectRegion(self, clipindex: int) -> None:
        self._regionSelected = clipindex
        self.update()

    def clearRegions(self) -> None:
        self._regions.clear()
        self._regionSelected = -1
        self.update()

    def initThumbs(self) -> None:
        framesize = self.parent.videoService.framesize()
        thumbsize = QSize(VideoService.ThumbSize.TIMELINE.value.height() * (framesize.width() / framesize.height()),
                          VideoService.ThumbSize.TIMELINE.value.height())
        positions, frametimes = [], []
        thumbs = int(math.ceil((self.rect().width() - (self.offset * 2)) / thumbsize.width()))
        for pos in range(thumbs):
            val = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                 (thumbsize.width() * pos) - self.offset,
                                                 self.rect().width() - (self.offset * 2))
            positions.append(val)
        positions[0] = 1000
        [frametimes.append(self.parent.delta2QTime(msec).toString(self.parent.timeformat)) for msec in positions]

        class ThumbWorker(QObject):
            completed = pyqtSignal(list)

            def __init__(self, media: str, times: list, size: QSize):
                super(ThumbWorker, self).__init__()
                self.media = media
                self.times = times
                self.size = size

            @pyqtSlot()
            def generate(self):
                frames = list()
                [frames.append(VideoService.captureFrame(self.media, frame, self.size)) for frame in self.times]
                self.completed.emit(frames)

        self.thumbsThread = QThread(self)
        self.thumbsWorker = ThumbWorker(self.parent.currentMedia, frametimes, thumbsize)
        self.thumbsWorker.moveToThread(self.thumbsThread)
        self.thumbsThread.started.connect(self.parent.sliderWidget.setLoader)
        self.thumbsThread.started.connect(self.thumbsWorker.generate)
        self.thumbsThread.finished.connect(self.thumbsThread.deleteLater, Qt.DirectConnection)
        self.thumbsWorker.completed.connect(self.buildTimeline)
        self.thumbsWorker.completed.connect(self.thumbsWorker.deleteLater, Qt.DirectConnection)
        self.thumbsWorker.completed.connect(self.thumbsThread.quit, Qt.DirectConnection)
        self.thumbsThread.start()

    @pyqtSlot(list)
    def buildTimeline(self, thumbs: list) -> None:
        thumbslayout = QHBoxLayout()
        thumbslayout.setSizeConstraint(QLayout.SetFixedSize)
        thumbslayout.setSpacing(0)
        thumbslayout.setContentsMargins(0, 16, 0, 0)
        for thumb in thumbs:
            thumblabel = QLabel()
            thumblabel.setStyleSheet('padding: 0; margin: 0;')
            thumblabel.setFixedSize(thumb.size())
            thumblabel.setPixmap(thumb)
            thumbslayout.addWidget(thumblabel)
        thumbnails = QWidget(self)
        thumbnails.setLayout(thumbslayout)
        filmlabel = QLabel()
        filmlabel.setObjectName('filmstrip')
        filmlabel.setFixedHeight(VideoService.ThumbSize.TIMELINE.value.height() + 2)
        filmlabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        filmlayout = QHBoxLayout()
        filmlayout.setContentsMargins(0, 0, 0, 16)
        filmlayout.setSpacing(0)
        filmlayout.addWidget(filmlabel)
        filmstrip = QWidget(self)
        filmstrip.setLayout(filmlayout)
        self.removeThumbs()
        self.parent.sliderWidget.addWidget(filmstrip)
        self.parent.sliderWidget.addWidget(thumbnails)
        self.thumbnailsOn = True
        self.initStyle()
        self.parent.sliderWidget.setLoader(False)
        if self.parent.newproject:
            self.parent.renderClipIndex()
            self.parent.newproject = False

    def removeThumbs(self) -> None:
        if self.parent.sliderWidget.count() == 3:
            stripWidget = self.parent.sliderWidget.widget(1)
            thumbWidget = self.parent.sliderWidget.widget(2)
            self.parent.sliderWidget.removeWidget(stripWidget)
            self.parent.sliderWidget.removeWidget(thumbWidget)
            stripWidget.deleteLater()
            thumbWidget.deleteLater()
            self.setObjectName('nothumbs')
            self.thumbnailsOn = False

    def errorHandler(self, error: str) -> None:
        self.logger.error(error)
        sys.stderr.write(error)

    def reloadThumbs(self) -> None:
        if self.parent.mediaAvailable and self.parent.thumbnailsButton.isChecked():
            if self.thumbnailsOn:
                self.parent.sliderWidget.hideThumbs()
            self.initThumbs()
            self.parent.renderClipIndex()

    @pyqtSlot()
    def on_rangeChanged(self) -> None:
        if self.parent.thumbnailsButton.isChecked():
            self.initThumbs()
        else:
            self.parent.sliderWidget.setLoader(False)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.parent.mediaAvailable:
            if event.angleDelta().y() > 0:
                self.parent.mpvWidget.frameBackStep()
            else:
                self.parent.mpvWidget.frameStep()
            event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        qApp.sendEvent(self.parent, event)

    def eventFilter(self, obj: QObject, event: QMouseEvent) -> bool:
        if event.type() == QEvent.MouseButtonRelease:
            if self.parent.mediaAvailable and self.isEnabled():
                newpos = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x() - self.offset,
                                                        self.width() - (self.offset * 2))
                self.setValue(newpos)
                self.parent.setPosition(newpos)
                self.parent.parent.mousePressEvent(event)
        return super(VideoSlider, self).eventFilter(obj, event)


class VideoSliderWidget(QStackedWidget):
    def __init__(self, parent, slider: VideoSlider):
        super(VideoSliderWidget, self).__init__(parent)
        self.parent = parent
        self.slider = slider
        self.loaderEffect = self.LoaderEffect()
        self.loaderEffect.setEnabled(False)
        self.setGraphicsEffect(self.loaderEffect)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.layout().setStackingMode(QStackedLayout.StackAll)
        self.addWidget(self.slider)

    def setLoader(self, enabled: bool=True) -> None:
        if hasattr(self.parent, 'toolbar') and self.parent.mediaAvailable:
            self.parent.toolbar.setEnabled(not enabled)
        self.slider.setEnabled(not enabled)
        self.loaderEffect.setEnabled(enabled)

    def hideThumbs(self) -> None:
        if self.count() == 3:
            self.widget(2).hide()
            self.widget(1).hide()
            self.slider.thumbnailsOn = False
            self.slider.initStyle()

    class LoaderEffect(QGraphicsEffect):
        def draw(self, painter: QPainter) -> None:
            if self.sourceIsPixmap():
                pixmap, offset = self.sourcePixmap(Qt.LogicalCoordinates, QGraphicsEffect.PadToEffectiveBoundingRect)
            else:
                pixmap, offset = self.sourcePixmap(Qt.DeviceCoordinates, QGraphicsEffect.PadToEffectiveBoundingRect)
                painter.setWorldTransform(QTransform())
            painter.setBrush(Qt.black)
            painter.drawRect(pixmap.rect())
            painter.setOpacity(0.2)
            painter.drawPixmap(offset, pixmap)
