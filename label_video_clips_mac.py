import sys
import os
import math
import csv
import re


from PyQt5.QtCore import Qt, QDir, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import *
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtGui import QKeySequence

__appname__ = 'Video Clips Labeler'

def get_vid_paths(dir, ext=('.mp4', '.mov', '.avi')):
    vid_paths = []
    
    for filename in os.listdir(dir):
        if filename.lower().endswith(ext):
            vid_paths.append(os.path.join(dir, filename))
    
    return vid_paths

def millisec_to_time(ms):
    milliseconds = math.floor((ms % 1000) / 100)  # one decimal point to sec
    seconds = math.floor((ms / 1000) % 60)
    minutes = math.floor(ms / (1000 * 60))  # minutes can be over 60
    return minutes, seconds, milliseconds

def time_to_millisec(time):
    m, s = time.split(':')
    s = s.split('.')[0]
    millisec = (int(m)*60 + int(s)) * 1000
    return millisec

def natural_sort(l): 
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(l, key=alphanum_key)

class ToggleButton(QPushButton):
    def __init__(self, text):
        QPushButton.__init__(self, text)
        self.setStyleSheet('background-color: gray')
        self.setCheckable(True)
        self.toggled.connect(self.toggle_button)

    @pyqtSlot(bool)
    def toggle_button(self, state):
        self.setStyleSheet('background-color: %s' % ({True: 'green', False: 'gray'}[state]))


class MainWindow(QMainWindow):

    duration_signal = pyqtSignal(int)

    def __init__(self):
        super().__init__()

        self.input_folder = ''
        self.input_files = []
        self.num_files = 0
        self.idx = 0
        self.clip_idx = 0

        self.interval = 1000  # in milliseconds
        self.label_buttons = []
        self.assigned_labels = {}
        self.output_filename_default = 'label'

        self.duration = [0, 0, 0]
        self.timestamp = []
        self.duration_signal.connect(self.update_duration)
        self.loop = True
        self.loop_start = 0
        self.loop_end = 0

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(__appname__)

        self.setMinimumSize(1250, 800)

        # File control buttons: open folder, previous file, next file
        self.openButton = QPushButton("Choose Video Folder")   
        self.openButton.setFixedHeight(24)
        self.openButton.clicked.connect(self.choose_folder)

        self.prevButton = QPushButton("Prev[W]")
        self.prevButton.setEnabled(False)
        self.prevButton.setFixedHeight(24)
        self.prevButton.clicked.connect(self.prev_vid)

        self.nextButton = QPushButton("Next[S]")
        self.nextButton.setFixedHeight(24)
        self.nextButton.clicked.connect(self.next_vid)
        self.nextButton.setEnabled(False)

        self.prev_shortcut = QShortcut(QKeySequence(Qt.Key_W), self)
        self.prev_shortcut.activated.connect(lambda: self.prev_vid())
        self.next_shortcut = QShortcut(QKeySequence(Qt.Key_S), self)
        self.next_shortcut.activated.connect(lambda: self.next_vid())

        fileControlLayout = QHBoxLayout()
        fileControlLayout.setContentsMargins(0, 0, 0, 0)
        fileControlLayout.addWidget(self.openButton)
        fileControlLayout.addWidget(self.prevButton)
        fileControlLayout.addWidget(self.nextButton)

        self.csvButton = QPushButton("Generate csv")
        self.csvButton.setFixedHeight(24)
        self.csvButton.clicked.connect(self.get_csv_filename)
        self.csvButton.setEnabled(False)

        # List of video files
        self.file_list_widget = QListWidget()
        file_list_layout = QVBoxLayout()
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.addLayout(fileControlLayout)
        file_list_layout.addWidget(self.csvButton)

        self.file_list_widget.itemDoubleClicked.connect(self.file_item_double_clicked)
        file_list_container = QWidget()
        file_list_container.setLayout(file_list_layout)
        self.file_dock = QDockWidget()
        self.file_dock.setObjectName('Video Files')
        self.file_dock.setWidget(file_list_container)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.file_dock)
        file_list_layout.addWidget(self.file_list_widget)

        # List of clips
        clipGroupBox = QGroupBox('TimeStamps - previous: press [A] | next: press [D]')
        clipGroupBox.setMaximumWidth(1000)
        clipGroupBox.setMaximumHeight(120)

        self.interval_sec = QLabel(self)
        self.interval_sec.setFixedHeight(24)
        self.interval_sec.setAlignment(Qt.AlignCenter)

        self.clip_list_widget = QListWidget()
        self.clip_list_widget.setFlow(QListView.LeftToRight)
        self.clip_list_widget.setFixedHeight(50)
        self.clip_list_widget.itemDoubleClicked.connect(self.clip_item_double_clicked)
        clip_list_layout = QVBoxLayout()
        clip_list_layout.addWidget(self.interval_sec)
        clip_list_layout.addWidget(self.clip_list_widget, Qt.AlignTop)
        clipGroupBox.setLayout(clip_list_layout)

        self.prev_clip_shortcut = QShortcut(QKeySequence(Qt.Key_A), self)
        self.prev_clip_shortcut.activated.connect(lambda: self.prev_clip())
        self.next_clip_shortcut = QShortcut(QKeySequence(Qt.Key_D), self)
        self.next_clip_shortcut.activated.connect(lambda: self.next_clip())
    
        # Label buttons
        labelGroupBox = QGroupBox('Label')
        labelGroupBox.setMaximumWidth(400)
        labelGroupBox.setMaximumHeight(120)

        self.label_button_0 = ToggleButton('0')        
        self.label_button_1 = ToggleButton('1')        
        self.label_button_2 = ToggleButton('2')
        self.label_button_0.setEnabled(False)
        self.label_button_1.setEnabled(False)
        self.label_button_2.setEnabled(False)

        self.label_button_0.clicked.connect(lambda: self.set_label(0))
        self.label_button_1.clicked.connect(lambda: self.set_label(1))
        self.label_button_2.clicked.connect(lambda: self.set_label(2))

        self.label_buttons = [self.label_button_0, self.label_button_1, self.label_button_2]

        labelLayout = QVBoxLayout()
        for lb in self.label_buttons:
            labelLayout.addWidget(lb)
        labelGroupBox.setLayout(labelLayout)

        clipLabelLayout = QHBoxLayout()
        clipLabelLayout.setContentsMargins(0, 0, 0, 0)
        clipLabelLayout.addWidget(clipGroupBox)
        clipLabelLayout.addWidget(labelGroupBox)

        # Video Player
        videoWidget = QVideoWidget()
        
        self.playButton = QPushButton()
        self.playButton.setEnabled(False)
        self.playButton.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.playButton.clicked.connect(self.toggle_play)
 
        self.positionSlider = QSlider(Qt.Horizontal)
        self.positionSlider.setRange(0, 0)
        self.positionSlider.setEnabled(False)
 
        self.play_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.play_shortcut.activated.connect(self.toggle_play)

        self.loopButton = QCheckBox('Loop Selected Part')
        self.loopButton.stateChanged.connect(self.chkLoop)
        self.loopButton.setChecked(False)
 
        # Video control buttons: play
        controlLayout = QHBoxLayout()
        controlLayout.setContentsMargins(0, 0, 0, 0)
        controlLayout.addWidget(self.playButton)
        controlLayout.addWidget(self.positionSlider)
        controlLayout.addWidget(self.loopButton)
 
        self.playtime = QLabel(self)
        self.playtime.setFixedHeight(20)
        self.playtime.setAlignment(Qt.AlignCenter)
        
        self.error = QLabel()
        self.error.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self.guide = QLabel(self)
        self.guide.setText(
            "[0] description for class 0 [1] description for class 1 [2] description for class 2")
        self.guide.setFixedWidth(900)
        self.guide.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(self.guide)
        layout.addWidget(videoWidget, Qt.AlignTop)
        layout.addLayout(controlLayout)
        layout.addWidget(self.playtime)
        layout.addLayout(clipLabelLayout)
        layout.addWidget(self.error, Qt.AlignTop)

        wid = QWidget(self)
        self.setCentralWidget(wid)
        wid.setLayout(layout)

        self.mediaPlayer = QMediaPlayer(None, QMediaPlayer.VideoSurface)
 
        self.mediaPlayer.setVideoOutput(videoWidget)
        self.mediaPlayer.setVolume(0)
        self.mediaPlayer.stateChanged.connect(self.mediaStateChanged)
        self.mediaPlayer.positionChanged.connect(self.positionChanged)
        self.mediaPlayer.durationChanged.connect(self.durationChanged)
        self.mediaPlayer.error.connect(self.handleError)


    def choose_folder(self):
        dir = QFileDialog.getExistingDirectory(self, "Choose Folder",
                                               QDir.homePath())
        self.input_folder = dir
        if dir:
            self.load_files(dir)

    def load_files(self, dir):
        self.input_files = get_vid_paths(dir)
        self.num_files = len(self.input_files)
        self.file_list_widget.clear()
        if self.input_files:
            for f in self.input_files:
                self.file_list_widget.addItem(f)
            self.file_list_widget.setCurrentRow(0)
        
            self.mediaPlayer.setMedia(
                QMediaContent(QUrl.fromLocalFile(self.input_files[0]))
            )

            self.playButton.setEnabled(True)
            self.prevButton.setEnabled(True)
            self.nextButton.setEnabled(True)
            for b in self.label_buttons:
                b.setEnabled(True)
            self.csvButton.setEnabled(True)

            self.get_interval()

    def chkLoop(self):
        if self.loopButton.isChecked():
            self.loop = True
        else:
            self.loop = False

    def get_interval(self):
        val, ok = QInputDialog().getInt(
            self, 'Set Clip Time Interval', 'Interval:', 1, 1, 10, 1)
        
        if ok:
            self.interval = val * 1000
            self.interval_sec.setText(f'Interval: {self.interval//1000} sec')
            self.update_duration(self.mediaPlayer.duration())

    def file_item_double_clicked(self, item):
        filepath = item.text()
        if filepath:
            self.idx = self.input_files.index(filepath)
            self.open_file(filepath)

    def open_file(self, filepath):
        if filepath != '':
            self.mediaPlayer.setMedia(QMediaContent(QUrl.fromLocalFile(filepath)))
            self.clip_idx = 0
            self.clip_item_changed()
 
    def prev_vid(self):
        if self.idx > 0:
            self.idx -= 1

            if self.idx < self.num_files:
                filepath = self.input_files[self.idx]                
                self.file_list_widget.setCurrentRow(self.idx)
                self.open_file(filepath)

    def next_vid(self):
        if self.idx < self.num_files - 1:
            self.idx += 1

            filepath = self.input_files[self.idx]
            self.file_list_widget.setCurrentRow(self.idx)
            self.open_file(filepath)

    def exitCall(self):
        sys.exit(app.exec_())
 
    def toggle_play(self):
        if self.mediaPlayer.state() == QMediaPlayer.PlayingState:
            self.mediaPlayer.pause()
        else:
            self.mediaPlayer.play()

    def update_label_buttons(self):
        vid_path = self.input_files[self.idx]
        vid_name = os.path.split(vid_path)[-1]
        clip_timestamp = self.timestamp[self.clip_idx]  # in milliseconds
        minute, sec, millisec = millisec_to_time(clip_timestamp)
        clip_timestamp_str = f'{minute:02d}:{sec:02d}.'

        if vid_name in self.assigned_labels.keys():
            if clip_timestamp_str in self.assigned_labels[vid_name].keys():
                label_history = self.assigned_labels[vid_name][clip_timestamp_str]
                for i, b in enumerate(self.label_buttons):
                    if i == label_history:
                        b.setChecked(True)
                    else:
                        b.setChecked(False)
            else:
                for b in self.label_buttons:
                    b.setChecked(False)
        else:
            for b in self.label_buttons:
                b.setChecked(False)
        
    def clip_item_changed(self):
        self.update_label_buttons()
        self.loop_start = self.timestamp[self.clip_idx]
        if self.clip_idx >= len(self.timestamp) - 1:
            self.loop_end = self.mediaPlayer.duration()
        else:
            self.loop_end = self.timestamp[self.clip_idx + 1]

    def clip_item_double_clicked(self, item):
        clip_start = time_to_millisec(item.text())
        clip_num = self.timestamp.index(clip_start)
        self.mediaPlayer.setPosition(clip_start)
        self.clip_idx = int(clip_num)-1
        self.clip_item_changed()

    def prev_clip(self):
        if self.clip_idx > 0:
            self.clip_idx -= 1
            self.clip_list_widget.setCurrentRow(self.clip_idx)
            ts = self.timestamp[self.clip_idx]
            self.mediaPlayer.setPosition(ts)
            self.clip_item_changed()
    
    def next_clip(self):
        if self.clip_idx < len(self.timestamp) - 1:
            self.clip_idx += 1
            self.clip_list_widget.setCurrentRow(self.clip_idx)
            ts = self.timestamp[self.clip_idx]
            self.mediaPlayer.setPosition(ts)
            self.clip_item_changed()

    def mediaStateChanged(self, state):
        self.update_play_button(state)

    def update_play_button(self, status):
        if status == QMediaPlayer.PlayingState:
            self.playButton.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        else:
            self.playButton.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
 
    def positionChanged(self, position):
        if self.loop and position > self.loop_end:
            self.mediaPlayer.setPosition(self.loop_start)
        else:
            self.update_position(position)

    def durationChanged(self, duration):
        self.duration_signal.emit(duration)
 
    def update_duration(self, duration):
        """ 
            1. Update slidebar for the selected video 
            2. Update clips
        """
        self.positionSlider.setRange(0, duration)
        minute, sec, millisec = millisec_to_time(duration)
        self.duration = [minute, sec, millisec]
        self.update_position(0)

        self.clip_list_widget.clear()

        clips = []
        for i in range(math.ceil(duration/self.interval)):
            clips.append(i * self.interval)
        
        if len(clips) > 1 and self.mediaPlayer.duration() - clips[-1] < self.interval:
            clips = clips[:-1]

        self.timestamp = clips

        if self.timestamp:
            for i, t in enumerate(self.timestamp):
                m, s, _ = millisec_to_time(t)
                t_str = f'{m:02d}:{s:02d}.'
                self.clip_list_widget.addItem(t_str)
            self.clip_list_widget.setCurrentRow(0)
            self.clip_idx = 0

    def update_position(self, position):
        """ Update the position of slider handle """
        self.positionSlider.setValue(position)
        minute, sec, millisec = millisec_to_time(position)
        dminute, dsec, dmillisec = self.duration
        self.playtime.setText(f'{minute:02d}:{sec:02d}.{millisec} / {dminute:02d}:{dsec:02d}.{dmillisec}')
 
    def handleError(self):
        self.playButton.setEnabled(False)
        self.error.setText("Error: " + self.mediaPlayer.errorString())

    def set_label(self, label):
        vid_path = self.input_files[self.idx]
        vid_name = os.path.split(vid_path)[-1]
        clip_timestamp = self.timestamp[self.clip_idx]  # in milliseconds
        minute, sec, millisec = millisec_to_time(clip_timestamp)
        clip_timestamp_str = f'{minute:02d}:{sec:02d}.'

        if vid_name in self.assigned_labels.keys():
            for i, button in enumerate(self.label_buttons):
                # change label
                if button.isChecked() and i != label:
                    button.setChecked(False)
                    del self.assigned_labels[vid_name][clip_timestamp_str]
            # clicked the same label -> toggle
            if clip_timestamp_str in self.assigned_labels[vid_name].keys():  
                del self.assigned_labels[vid_name][clip_timestamp_str]
            # no label was selected for the clip
            else:
                self.assigned_labels[vid_name][clip_timestamp_str] = label
        # no label was selected for the video
        else:
            self.assigned_labels[vid_name] = {}
            self.assigned_labels[vid_name][clip_timestamp_str] = label

    def get_csv_filename(self):
        csv_filename, ok = QInputDialog.getText(self, '', 'Enter File Name:')
        if ok:
            if csv_filename == '':
                csv_filename = self.output_filename_default
            self.generate_csv(csv_filename)

    def generate_csv(self, csv_filename):
        output_dir = os.path.join(self.input_folder, 'output')
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, f'{csv_filename}.csv')

        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f, delimiter=',')
            writer.writerow(['Video', 'TimeStamp', 'Label'])
            if self.assigned_labels:
                vid_name_sorted = natural_sort(self.assigned_labels)
                for vid_name in vid_name_sorted:
                    clips = self.assigned_labels[vid_name]
                    for ts, score in sorted(clips.items()):
                        writer.writerow([vid_name, ts, score])
        self.show_csv_msg(csv_path)

    def show_csv_msg(self, path):
        QMessageBox.information(self, 'generated csv', f'Labels saved to {path}')

 
if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())