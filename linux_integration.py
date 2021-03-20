import os
from PyQt5.QtCore import QObject, pyqtProperty, Q_CLASSINFO, pyqtSlot, QMetaType, pyqtSignal, QTimer
from PyQt5.QtDBus import QDBusConnection, QDBusAbstractAdaptor, QDBusMessage, QDBusObjectPath, QDBusArgument

# Copied a ton of this from https://raw.githubusercontent.com/ripdog/vapoursonic
# Thank you!


class mprisIntegration(QObject):
	def __init__(self, playbackController, current_episode_data, ep_play):
		super(mprisIntegration, self).__init__()
		mprisMain(self, playbackController)
		mprisPlayer(self, playbackController, current_episode_data, ep_play)
		self.connection = QDBusConnection.sessionBus()
		self.connection.registerObject("/org/mpris/MediaPlayer2", self)
		self.serviceName = "org.mpris.MediaPlayer2.kodkast"
		self.connection.registerService(self.serviceName)


class mprisMain(QDBusAbstractAdaptor):
	Q_CLASSINFO("D-Bus Interface", "org.mpris.MediaPlayer2")
	
	def __init__(self, parent, playbackController):
		super(mprisMain, self).__init__(parent)
		self.setAutoRelaySignals(True)
		self.playbackController = playbackController

	@pyqtProperty(bool)
	def CanQuit(self):
		return False
	
	@pyqtProperty(bool)
	def CanRaise(self):
		return True
	
	@pyqtProperty(bool)
	def HasTrackList(self):
		# return True TODO
		return False
	
	@pyqtProperty(str)
	def Identity(self):
		return 'kodkast'
	
	@pyqtProperty(str)
	def DesktopEntry(self):
		return 'kodkast'
	
	@pyqtProperty('QStringList')
	def SupportedUriSchemes(self):
		return ['https']
	
	@pyqtProperty('QStringList')
	def SupportedMimeTypes(self):
		return ['audio/mp3']
	
	@pyqtProperty('QStringList')
	def SupportedInterfaces(self):
		return ['player']


# noinspection PyArgumentList
def buildMetadataDict(episode):
	return {
		'mpris:trackid': QDBusObjectPath(
			'/kodkast/{}'.format(episode['id'])
		),
		'xesam:trackNumber': episode['track'],
		'xesam:title': episode['title'],
		'xesam:artist': episode['artist'],
		'mpris:length': episode['duration'] * 1000000,  # convert to microseconds
		'mpris:artUrl': episode['coverArt'] if 'coverArt' in episode else ""
	}


class mprisPlayer(QDBusAbstractAdaptor):
	Q_CLASSINFO("D-Bus Interface", "org.mpris.MediaPlayer2.Player")
	
	def __init__(self, parent, playbackController, current_episode_data, ep_play):
		super(mprisPlayer, self).__init__(parent)
		self.setAutoRelaySignals(True)
		self.playbackController = playbackController
		self.current_episode_data = current_episode_data
		self.ep_play = ep_play
		self.helper = MPRIS2Helper()
		self._emitMetadata()

		self.ep_play.clicked.connect(self._emitPauseUpdate)
	
	@pyqtSlot()
	def Play(self):
		self.ep_play.clicked.emit()
	
	@pyqtSlot()
	def Pause(self):
		self.ep_play.clicked.emit()
	
	@pyqtProperty("QMap<QString, QVariant>")
	def Metadata(self):
		if not self.current_episode_data:
			metadata = {'mpris:trackid': QDBusObjectPath(
				'/kodkast/notrack'
			)}
			return metadata
		return buildMetadataDict(self.current_episode_data)

	def _emitMetadata(self, **args):
		self.helper.PropertiesChanged(
			'org.mpris.MediaPlayer2.Player', 'Metadata', buildMetadataDict(self.current_episode_data)
		)
	
	def _emitPauseUpdate(self):
		pb_status = self.PlaybackStatus
		self.helper.PropertiesChanged("org.mpris.MediaPlayer2.Player",
		                              "PlaybackStatus",
									  pb_status
									  )
		self.helper.PropertiesChanged("org.mpris.MediaPlayer2.Player",
		                              "Position",
									  pb_status
									  )
		self.playbackController.get_time() * 1000
	
	@pyqtProperty(str)
	def PlaybackStatus(self):
		try:
			if self.playbackController.is_playing():
				return 'Playing'
			else:
				return 'Paused'
		except:
			return 'Stopped'

	@pyqtSlot("qlonglong")
	def Position(self):
		return self.playbackController.get_time() * 1000

	@pyqtProperty(float)
	def Rate(self):
		return self.playbackController.get_rate()
	
	@Rate.setter
	def Rate(self, rate):
		self.playbackController.set_rate(rate)
	
	@pyqtProperty(float)
	def MinimumRate(self):
		return 1.0
	
	@pyqtProperty(float)
	def MaximumRate(self):
		return 2.0

	@pyqtSlot(QDBusObjectPath, "qlonglong")
	def SetPosition(self, trackId, position):
		if trackId.path() == '/kodkast/{}'.format(self.current_episode_data['id']):
			self.playbackController.set_time(position / 1000)

	@pyqtProperty("qlonglong")
	def Position(self):
		print("position set")
		try:
			return self.playbackController.get_time() * 1000
		except:
			return 0.0

	@pyqtSlot("qlonglong")
	def Seek(self, offset):
		# newtime = self.playbackController.player.time_pos + (offset / 1000000)
		# self.playbackController.setTrackProgress(newtime)
		pass
	
	Seeked = pyqtSignal('qlonglong')
	
	def _emitSeeked(self, **args):
		self.Seeked.emit(self.playbackController.get_time() * 1000)

	@pyqtProperty(bool)
	def CanPause(self):
		if self.PlaybackStatus != 'Stopped':
			return True
		else:
			return False

	@pyqtProperty(bool)
	def CanPlay(self):
		if self.PlaybackStatus != 'Stopped':
			return True
		else:
			return False

	@pyqtProperty(bool)
	def CanControl(self):
		return True

	@pyqtProperty("qlonglong")
	def Position(self):
		return self.playbackController.get_time() * 1000
	
	@pyqtSlot()
	def PlayPause(self):
		self.ep_play.clicked.emit()


# noinspection PyCallByClass
class MPRIS2Helper(object):
	def __init__(self):
		self.signal = QDBusMessage.createSignal(
			"/org/mpris/MediaPlayer2",
			"org.freedesktop.DBus.Properties",
			"PropertiesChanged"
		)
	
	def PropertiesChanged(self, interface, prop, values):
		"""Sends PropertiesChanged signal through sessionBus.
		Args:
			interface: interface name
			prop: property name
			values: current property value(s)
		"""
		emptyStringListArg = QDBusArgument()
		emptyStringListArg.add([""], QMetaType.QStringList)
		self.signal.setArguments([interface, {prop: values}, emptyStringListArg])
		QDBusConnection.sessionBus().send(self.signal)
