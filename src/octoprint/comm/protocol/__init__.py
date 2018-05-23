# coding=utf-8
from __future__ import absolute_import, print_function, unicode_literals

__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2015 The OctoPrint Project - Released under terms of the AGPLv3 License"

from octoprint.util.listener import ListenerAware
from octoprint.comm.transport import TransportListener, TransportState

from octoprint.util import to_unicode

import logging

class Protocol(ListenerAware, TransportListener):

	supported_jobs = []

	def __init__(self):
		super(Protocol, self).__init__()

		self._logger = logging.getLogger(__name__)
		self._protocol_logger = logging.getLogger("PROTOCOL")
		self._state = ProtocolState.DISCONNECTED

		self._job = None
		self._transport = None

	@property
	def state(self):
		return self._state

	@state.setter
	def state(self, new_state):
		old_state = self._state
		if old_state == new_state:
			return

		self._state = new_state

		name = "_on_state_{}".format(new_state)
		method = getattr(self, name, None)
		if method is not None:
			method(old_state)

		self.process_protocol_log("--- Protocol state changed from '{}' to '{}'".format(old_state, new_state))
		self.notify_listeners("on_protocol_state", self, old_state, new_state)

	def connect(self, transport, transport_args=None, transport_kwargs=None):
		if self.state not in (ProtocolState.DISCONNECTED, ProtocolState.DISCONNECTED_WITH_ERROR):
			raise ProtocolAlreadyConnectedError("Already connected, disconnect first")

		self.process_protocol_log("--- Protocol {} connecting via transport {}...".format(self,
		                                                                                  transport))

		if transport_args is None:
			transport_args = []
		if transport_kwargs is None:
			transport_kwargs = dict()

		self._transport = transport
		self._transport.register_listener(self)

		if self._transport.state == TransportState.DISCONNECTED:
			self._transport.connect(*transport_args, **transport_kwargs)
		self.state = ProtocolState.CONNECTING

	def disconnect(self, error=False):
		if self.state in (ProtocolState.DISCONNECTED, ProtocolState.DISCONNECTED_WITH_ERROR, ProtocolState.DISCONNECTING):
			raise ProtocolNotConnectedError("Already disconnecting or disconnected")

		self.state = ProtocolState.DISCONNECTING

		self.process_protocol_log("--- Protocol {} disconnecting from transport {}...".format(self,
		                                                                                      self._transport))

		self._transport.unregister_listener(self)
		if self._transport.state == TransportState.CONNECTED:
			self._transport.disconnect()

		if error:
			self.state = ProtocolState.DISCONNECTED_WITH_ERROR
		else:
			self.state = ProtocolState.DISCONNECTED

	def process(self, job, position=0, tags=None):
		if not job.can_process(self):
			raise ValueError("Job {} cannot be processed with protocol {}".format(job, self))
		self._job = job
		self._job.register_listener(self)
		self._job.process(self, position=position, tags=tags)

	def pause_processing(self, tags=None):
		if self._job is None or self.state != ProtocolState.PRINTING:
			return
		self.state = ProtocolState.PAUSED

	def resume_processing(self, tags=None):
		if self._job is None or self.state != ProtocolState.PAUSED:
			return
		self.state = ProtocolState.PRINTING

	def cancel_processing(self, error=False, tags=None):
		if self._job is not None and self.state in (ProtocolState.PRINTING, ProtocolState.PAUSED):
			self._job.cancel(error=error)
		self.state = ProtocolState.CONNECTED

	def can_send(self):
		return True

	def send_commands(self, command_type=None, *commands):
		pass

	def repair(self):
		pass

	def on_job_started(self, job):
		self.state = ProtocolState.PRINTING

	def on_job_done(self, job):
		self._job_processed(job)

	def on_job_cancelled(self, job):
		self._job_processed(job)

	def on_job_failed(self, job):
		self._job_processed(job)

	def _job_processed(self, job):
		self._job.unregister_listener(self)
		self.state = ProtocolState.CONNECTED

	def on_transport_disconnected(self, transport, error=None):
		self.disconnect(error=error is not None)

	def on_transport_log_received_data(self, transport, data):
		message = "<<< {}".format(to_unicode(data, errors="replace").strip())
		self.process_protocol_log(message)

	def on_transport_log_sent_data(self, transport, data):
		message = ">>> {}".format(to_unicode(data, errors="replace").strip())
		self.process_protocol_log(message)

	def on_transport_log_message(self, transport, data):
		message = "--- {}".format(to_unicode(data, errors="replace").strip())
		self.process_protocol_log(message)

	def process_protocol_log(self, message):
		self._protocol_logger.info(message)
		self.notify_listeners("on_protocol_log", self, message)

	def __str__(self):
		return self.__class__.__name__

class ProtocolState(object):
	CONNECTING = "connecting"
	CONNECTED = "connected"
	DISCONNECTING = "disconnecting"
	DISCONNECTED = "disconnected"
	PRINTING = "printing"
	CANCELLING = "cancelling"
	PAUSING = "pausing"
	PAUSED = "paused"
	ERROR = "error"
	DISCONNECTED_WITH_ERROR = "disconnected_with_error"

class ProtocolAlreadyConnectedError(Exception):
	pass

class ProtocolNotConnectedError(Exception):
	pass

class ThreeAxisProtocolMixin(object):
	def move(self, x=None, y=None, z=None, feedrate=None, relative=False):
		pass

	def home(self, x=False, y=False, z=False):
		pass

	def change_tool(self, tool):
		pass


class ThreeDPrinterProtocolMixin(ThreeAxisProtocolMixin):
	def move(self, x=None, y=None, z=None, e=None, feedrate=None, relative=False):
		pass

	def set_feedrate_multiplier(self, multiplier):
		pass

	def set_extrusion_multiplier(self, multiplier):
		pass

	def set_extruder_temperature(self, temperature, tool=None, wait=False):
		pass

	def set_bed_temperature(self, temperature, wait=False):
		pass


class FanControlProtocolMixin(object):

	def set_fan_speed(self, speed):
		pass

	def get_fan_speed(self, speed):
		pass


class MotorControlProtocolMixin(object):

	def enable_motors(self):
		self.set_motor_state(True)

	def disable_motors(self):
		self.set_motor_state(False)

	def set_motor_state(self, enabled):
		pass

	def get_motor_state(self):
		pass


class PowerControlProtocolMixin(object):

	def enable_power(self):
		self.set_power_state(True)

	def disable_power(self):
		self.set_power_state(False)

	def set_power_state(self, enabled):
		pass

	def get_power_state(self):
		return None


class FileAwareProtocolMixin(object):

	def init_file_storage(self):
		pass

	def eject_file_storage(self):
		pass

	def list_files(self):
		pass

	def start_file_print(self, name, position=0, tags=None):
		pass

	def pause_file_print(self):
		pass

	def resume_file_print(self):
		pass

	def get_file_print_status(self):
		pass


class FileManagementProtocolMixin(FileAwareProtocolMixin):

	def delete_file(self, name):
		pass


class FileStreamingProtocolMixin(FileManagementProtocolMixin):

	def record_file(self, name, job):
		pass

	def stop_recording_file(self):
		pass


class ProtocolListener(object):

	def on_protocol_state(self, protocol, old_state, new_state):
		pass

	def on_protocol_temperature(self, protocol, temperatures):
		pass

	def on_protocol_log(self, protocol, message):
		pass


class FileAwareProtocolListener(object):

	def on_protocol_file_storage_available(self, protocol, available):
		pass

	def on_protocol_file_list(self, protocol, files):
		pass

	def on_protocol_file_status(self, protocol, pos, total):
		pass

	def on_protocol_file_print_started(self, protocol, name, size):
		pass

	def on_protocol_file_print_done(self, protocol):
		pass
