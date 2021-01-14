import feedparser
import sys
import time
import vlc
import urllib.request
import os
import peewee
from pyqtspinner.spinner import WaitingSpinner
from models import PodcastDB, EpisodeDB
from datetime import datetime
from PyQt5 import QtWidgets as qtw
from PyQt5 import QtGui as qtg
from PyQt5 import QtCore as qtc

class QJumpSlider(qtw.QSlider):
    def __init__(self, parent = None):
        super(QJumpSlider, self).__init__(parent)
     
    def mousePressEvent(self, event):
        #Jump to click position
        mw.set_position(qtw.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width()))
        self.setValue(qtw.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width()))
     
    def mouseMoveEvent(self, event):
        #Jump to pointer position while moving
        mw.set_position(qtw.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width()))
        self.setValue(qtw.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width()))


class QClickLabel(qtw.QLabel):
    clicked = qtc.pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        qtw.QLabel.mousePressEvent(self, event)


class MainWindow(qtw.QMainWindow):

    def __init__(self):
        """MainWindow Constructor"""
        super().__init__()
        
        self.setWindowTitle('Kodkast')
        self.setFixedHeight(600)
        self.resize(350, 600)

        self.track = None
        self.player = None
        self.is_paused = False
        self.ptt_to_prt = False
        self.playback_speed_val = 1

        self.podcasts_old = []

        self.initiate_database()

        self.build_menu_bar()
        self.build_library_view()

        self.show()

    def initiate_database(self):
        try:
            PodcastDB.create_table()
        except peewee.OperationalError:
            print("PodcastDB already exists!")
        
        try:
            EpisodeDB.create_table()
        except peewee.OperationalError:
            print("EpisodeDB already exists!")

    def build_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction('Quit', qtw.QApplication.quit, qtg.QKeySequence.Quit)

        # podcasts_menu = menubar.addMenu("Podcasts")
        # add_podcast_action = podcasts_menu.addAction('Add a new podcast', self.add_podcast)
        # add_podcast_action.setShortcut('Ctrl+A')

        episodes_menu = menubar.addMenu("Episodes")
        self.refresh_episodes_action = episodes_menu.addAction('Refresh episode list', self.load_episodes_from_feed)
        self.refresh_episodes_action.setShortcut('Ctrl+R')
        self.refresh_episodes_action.setEnabled(False)

    def build_library_view(self):
        library_layout = qtw.QWidget()
        library_layout.setLayout(qtw.QVBoxLayout())

        lib_title = qtw.QLabel('Library')
        self.lib_podcasts = qtw.QListWidget()
        self.lib_podcasts.doubleClicked.connect(lambda: self.build_episode_view(self.lib_podcasts.currentItem().text()))
        self.lib_add = qtw.QPushButton('Add Podcast', clicked=self.add_podcast)
        self.spinner = WaitingSpinner(self)

        library_layout.layout().addWidget(lib_title)
        library_layout.layout().addWidget(self.lib_podcasts)
        library_layout.layout().addWidget(self.lib_add)
        library_layout.layout().addWidget(self.spinner)
        self.setCentralWidget(library_layout)

        self.refresh_podcast_list()
    
    def refresh_podcast_list(self):
        query = PodcastDB.select()
        self.lib_podcasts.clear()
        for podcast in query:
            self.lib_podcasts.addItem(podcast.title)

    def add_podcast(self):
        self.toggle_loading()
        ap_url, ok = qtw.QInputDialog.getText(self, 'Add a Podcast', "Enter the podcast's URL:")
        if ok:
            time.sleep(1.5)
            feed = feedparser.parse(ap_url).feed
            if hasattr(feed, "title"):
                if hasattr(feed, "image"):
                    query = PodcastDB.select().where(PodcastDB.title == feed.title)
                    if query.exists():
                        exists_msg = qtw.QMessageBox()
                        exists_msg.setIcon(qtw.QMessageBox.Information)
                        exists_msg.setWindowTitle("Already Exists")
                        exists_msg.setText("You are already subscribed to that podcast.")
                        exists_msg.exec_()
                    else:
                        PodcastDB.create(title=feed.title, url=ap_url, image=feed.image['href'])
                else:
                    # TODO add a default image if podcast doesn't have one
                    pass
                self.refresh_podcast_list()
        self.toggle_loading()

    def build_episode_view(self, current_podcast):
        self.current_podcast = PodcastDB.select().where(PodcastDB.title==current_podcast).get()
        episode_layout = qtw.QWidget()
        episode_layout.setLayout(qtw.QVBoxLayout())

        back_to_pod_list = qtw.QPushButton("⬅", clicked=self.build_library_view)
        back_to_pod_list.setFixedWidth(50)
        title_label = qtw.QLabel(self.current_podcast.title)
        self.ep_list = qtw.QListWidget()
        self.ep_list.doubleClicked.connect(lambda: self.build_play_view(self.ep_list.currentItem().text()))
        self.ep_list_play = qtw.QPushButton("Play", clicked=lambda: self.build_play_view(self.ep_list.currentItem().text()))
        self.spinner = WaitingSpinner(self)

        episode_layout.layout().addWidget(back_to_pod_list)
        episode_layout.layout().addWidget(title_label)
        episode_layout.layout().addWidget(self.ep_list)
        episode_layout.layout().addWidget(self.ep_list_play)
        episode_layout.layout().addWidget(self.spinner)
        self.setCentralWidget(episode_layout)
        
        query = EpisodeDB.select().where(EpisodeDB.podcast == self.current_podcast)
        if query.exists():
            # If podcast episode lists exists, load it.
            self.refresh_episode_list()
        else:
            # Otherwise, build a new list from the feed.
            self.load_episodes_from_feed()
        self.refresh_episodes_action.setEnabled(True)

    def load_episodes_from_feed(self):
        for episode in feedparser.parse(self.current_podcast.url).entries:
            published_date = datetime.fromtimestamp(time.mktime(episode.published_parsed))
            query = EpisodeDB.select().where(EpisodeDB.url == self.get_episode_url(episode))
            if not query.exists():
                if hasattr(episode, "itunes_duration"):
                    EpisodeDB.create(
                        podcast=PodcastDB.get(PodcastDB.title==self.current_podcast.title),
                        title=episode.title,
                        pub_date=published_date,
                        url=self.get_episode_url(episode),
                        image=episode.image['href'],
                        duration=episode.itunes_duration,
                        bookmark=0,
                    )
                else:
                    EpisodeDB.create(
                        podcast=PodcastDB.get(PodcastDB.title==self.current_podcast.title),
                        title=episode.title,
                        pub_date=published_date,
                        url=self.get_episode_url(episode),
                        image=episode.image['href'],
                        bookmark=0,
                    )
            self.refresh_episode_list()

    def refresh_episode_list(self):
        query = EpisodeDB.select().where(EpisodeDB.podcast == self.current_podcast)
        self.ep_list.clear()
        for episode in query:
            self.ep_list.addItem(episode.title)

    def build_play_view(self, current_episode):
        self.refresh_episodes_action.setEnabled(False)
        self.current_episode = EpisodeDB.select().where(EpisodeDB.title == current_episode).get()
        play_layout = qtw.QWidget()
        play_layout.setLayout(qtw.QVBoxLayout())

        back_to_ep_list = qtw.QPushButton("⬅", clicked=self.back_to_episode_list)
        back_to_ep_list.setFixedWidth(50)
        ep_image_display = qtw.QLabel()
        headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',}
        request=urllib.request.Request(self.current_episode.image, None, headers)
        response = urllib.request.urlopen(request)
        url_image = response.read()
        # url_image = urllib.request.urlopen(self.current_episode.image).read()
        ep_image = qtg.QPixmap()
        ep_image.loadFromData(url_image)
        # scaled_width = play_layout.frameGeometry().width()
        ep_image_display.setPixmap(ep_image)
        ep_image_display.setScaledContents(True)
        ep_image_display.setFixedSize(300, 300)
        # ep_image_display.move(100, 100)
        # ep_image_display.setAlignment(qtc.Qt.AlignCenter)
        podcast_title = qtw.QLabel()
        podcast_title.setFixedWidth(300)
        episode_title = qtw.QLabel()
        episode_title.setFixedWidth(300)
        self.position_elapsed_time = qtw.QLabel("00:00")
        self.position_slider = QJumpSlider(qtc.Qt.Horizontal)
        self.position_slider.setMaximum(1000)
        self.position_total_time = QClickLabel()
        self.position_total_time.clicked.connect(self.position_total_time_clicked)
        self.ep_play = qtw.QPushButton("►", clicked=lambda: self.play_episode())
        ep_skip_back = qtw.QPushButton("⟲", clicked=self.skip_back)
        ep_skip_fwd = qtw.QPushButton("⟳", clicked=self.skip_forward)
        self.playback_speed_btn = qtw.QPushButton(f"{self.playback_speed_val}x", clicked=self.set_playback_speed)
        self.playback_speed_btn.setFixedWidth(50)

        self.timer = qtc.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_ui)

        controls_layout = qtw.QWidget()
        controls_layout.setLayout(qtw.QHBoxLayout())
        controls_layout.layout().addWidget(ep_skip_back)
        controls_layout.layout().addWidget(self.ep_play)
        controls_layout.layout().addWidget(ep_skip_fwd)

        position_layout = qtw.QWidget()
        position_layout.setLayout(qtw.QHBoxLayout())
        position_layout.layout().addWidget(self.position_elapsed_time)
        position_layout.layout().addWidget(self.position_slider)
        position_layout.layout().addWidget(self.position_total_time)

        play_layout.layout().addWidget(back_to_ep_list)
        play_layout.layout().addWidget(ep_image_display)
        play_layout.layout().addWidget(podcast_title)
        play_layout.layout().addWidget(episode_title)
        play_layout.layout().addWidget(position_layout)
        play_layout.layout().addWidget(controls_layout)
        play_layout.layout().addWidget(self.playback_speed_btn)
        self.setCentralWidget(play_layout)

        if self.track != self.current_episode.url:
            self.track = self.current_episode.url
            if self.player and self.player.is_playing():
                self.player.stop()
            self.player = vlc.MediaPlayer(self.track)
            podcast_title.setText(self.current_podcast.title)
            episode_title.setText(self.current_episode.title)
            self.is_paused = False
            self.play_episode()
        else:
            if self.player and self.player.is_playing():
                self.timer.start()
                self.ep_play.setText("⏸︎")

    def play_episode(self):
        if not self.player.is_playing():
            if self.is_paused:
                self.player.pause()
                self.is_paused = False
                self.ep_play.setText("⏸︎")
            else:
                self.player.play()
                self.ep_play.setText("⏸︎")
                while not self.player.is_playing():
                    time.sleep(0.5)
                if self.current_episode.bookmark != 0:
                    self.player.set_time(self.current_episode.bookmark)
                self.get_total_track_time()
            self.player.set_rate(self.playback_speed_val)
            self.timer.start()
        else:
            self.ep_play.setText("►")
            self.player.pause()
            self.is_paused = True
            self.timer.stop()

    def back_to_episode_list(self):
        self.timer.stop()
        self.build_episode_view(self.current_podcast.title)

    def get_total_track_time(self):
        '''
        Find the total length of the track.
        Display the length in the label to the right of the
        position_slider.
        '''
        self.total_track_length = self.player.get_length() / 1000
        length_gmtime = time.gmtime(self.total_track_length)
        self.ttl_string = time.strftime("%-H:%M:%S", length_gmtime)
        self.position_total_time.setText(self.ttl_string)

    def position_total_time_clicked(self):
        if self.ptt_to_prt:
            self.ptt_to_prt = False
            self.position_total_time.setText(self.ttl_string)
        else:
            self.ptt_to_prt = True

    def skip_back(self):
        if self.player and self.player.is_playing():
            rewind = self.player.get_time() - 10000
            if rewind < 0:
                rewind = 0
            self.player.set_time(rewind)

    def skip_forward(self):
        if self.player and self.player.is_playing():
            self.player.set_time(self.player.get_time() + 15000)

    def set_position(self, clicked_pos):
        '''
        Set the place in the audio track based on the slider.
        '''
        self.timer.stop()
        self.player.set_position(clicked_pos / 1000)
        self.timer.start()
    
    def set_playback_speed(self):
        if self.player:
            self.playback_speed_val += .25
            if self.playback_speed_val > 2:
                self.playback_speed_val = 1
            self.player.set_rate(self.playback_speed_val)
            self.playback_speed_btn.setText(f"{self.playback_speed_val}x")

    def update_ui(self):
        '''
        Update the slider and other UI elements while the audio is playing.
        '''
        track_position = int(self.player.get_position() * 1000)
        self.position_slider.setValue(track_position)

        # Show track time elapsed
        track_time_elapsed = self.player.get_time() / 1000
        tte_gmtime = time.gmtime(track_time_elapsed)
        if self.total_track_length >= 3600:
            tte_string = time.strftime("%-H:%M:%S", tte_gmtime)
        else:
            tte_string = time.strftime("%M:%S", tte_gmtime)
        self.position_elapsed_time.setText(tte_string)

        # If the user chose to display the remaining track time
        if self.ptt_to_prt:
            time_remaining = self.total_track_length - track_time_elapsed
            tr_gmtime = time.gmtime(time_remaining)
            if self.total_track_length >= 3600:
                tte_string = time.strftime("%-H:%M:%S", tr_gmtime)
            else:
                tte_string = time.strftime("%M:%S", tr_gmtime)
            self.position_total_time.setText(tte_string)

        # Every 5 seconds, update database to save place in podcast
        rounded_elapsed = int(round(track_time_elapsed, 0))
        if rounded_elapsed % 5 == 0:
            # Don't save the same timestamp twice
            if 'already_saved' not in locals() or already_saved != rounded_elapsed:
                self.current_episode.bookmark = self.player.get_time()
                self.current_episode.save()
                already_saved = rounded_elapsed

        # If no media is playing, stop the timer
        if not self.player.is_playing():
            self.timer.stop()
            # If player not playing and it's not paused the track is finished
            if not self.is_paused:
                self.ep_play.setText("►")

    def toggle_loading(self):
        if self.spinner.isSpinning:
            self.setEnabled(True)
            self.spinner.stop()
        else:
            self.spinner.start()
            self.setEnabled(False)
    
    @staticmethod
    def get_episode_url(episode):
        links = episode["links"]
        for link in links:
            if "audio" in link["type"]:
                return link["href"]

if __name__ == '__main__':
    app = qtw.QApplication(sys.argv)
    mw = MainWindow()
    sys.exit(app.exec())
