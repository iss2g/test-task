from itertools import count as sequence
import asyncio

from time_funcs import *
from binance_interface.ws.connection import Websocket_binance as Connection_ws
from binance_interface.ws.connections_mngr_exceptions import *






# [BEGIN:Connection_info]
class Connection_info:
	def __init__(self, metrics_requests_local, metrics_requests_global, metrics_connections, deadline_td=None,
				 retire_td=None, silence_td=None, unreliable_td=None):
		self.metrics_requests = self.join_metrics_requests(metrics_requests_local, metrics_requests_global)
		self.metrics_connections = metrics_connections

		self.deadline_sd = td_to_sd(deadline_td)
		self.retire_sd = td_to_sd(retire_td)
		self.silence_sd = td_to_sd(silence_td)
		self.unreliable_sd = td_to_sd(unreliable_td)

		self.streams_map = {}
		self.tracks_map = {}

		self.to_be_closed = False

		self.to_created_state()

	# {__INIT__INTERNAL}
	def join_metrics_requests(self, metrics_requests_local, metrics_requests_global):
		return metrics_requests_local

	#
	# {INFO_INTERFACE}
	##{STATE_INFO}
	def get_state(self):
		return self.state

	def is_closed(self):
		return self.get_state() == 'closed'

	def is_created(self):
		return self.get_state() == 'created'

	def is_connecting(self):
		return self.get_state() == 'connecting'

	def is_connected(self):
		return self.get_state() == 'connected'

	def is_active(self):
		return self.get_state() == 'active'

	##
	##{BAD_TAGS_INFO}
	def is_retire(self):
		"""
		True если до deadline осталось меньше кстановленого срока
		"""
		if not self.deadline:
			return False

		tm = time_s()
		if self.deadline - tm < self.retire_sd:
			return True
		else:
			return False

	def is_silent(self):
		"""
		True если соендинение не получает сообщений в течении 2 минут
		False  если получало
		"""
		tm = time_s()
		if tm - self.external_msg_tm > self.silence_sd:
			return True
		else:
			return False

	def is_unreliable(self):
		"""
		True если в какой-то моемент в прошлом соендинение не получало сообщений в течении 5 минут и более
		False если такого не было
		"""
		if self.max_silence_sd > self.unreliable_sd:
			return True
		else:
			return False

	def is_to_be_closed(self):
		return self.to_be_closed

	def get_bad_tags(self):
		bad_tags = []
		if self.is_retire():
			bad_tags.append('retire')
		if self.is_silent():
			bad_tags.append('silent')
		if self.is_unreliable():
			bad_tags.append('unreliable')
		if self.is_to_be_closed():
			bad_tags.append('to_be_closed')
		if self.is_closed():
			bad_tags.append('closed')
		return bad_tags

	def is_ok(self):
		return not self.get_bad_tags()
		
	def is_empty(self):
		return not self.streams_map 

	##
	##{REQUESTS_LIMITS_INFO}
	def allowed_number_get(self):
		return self.allowed_number('get')

	def allowed_number_sub(self):
		return self.allowed_number('sub')

	def allowed_number_sub_residue(self):
		sub_metrics = self.metrics_requests['sub']
		number_max = sub_metrics.get('number_max')
		number = sub_metrics['number']
		number_add = sub_metrics['number_add']
		return number_max - number - number_add

	def allowed_number_unsub(self):
		return self.allowed_number('unsub')

	def allowed_number(self, req_tp):
		req_metrics = self.metrics_requests.get(req_tp)
		tm = time_s()
		default_number = 1
		return_number = None
		if not req_metrics:
			return default_number

		base = req_metrics.get('base')
		if base:
			base_metrics = self.metrics_requests.get(req_metrics['base'])
			period_count_max = base_metrics.get('period_count_max')
			base_allowed = True
			if period_count_max:
				period = base_metrics['period']
				period_count = base_metrics['period_count']
				period_count_add = base_metrics['period_count_add']
				period_duration = base_metrics['period_duration']

				period_is_actual = True if period + period_duration > tm else False

				if period_is_actual:
					if period_count + period_count_add == period_count_max:
						return 0
					elif period_count == period_count_max:
						return 0
					elif period_count + period_count_add < period_count_max:
						pass

				else:
					if period_count_add == period_count_max:
						return 0
					elif period_count_add < period_count_max:
						pass

		period_count_max = req_metrics.get('period_count_max')
		if period_count_max:
			period = req_metrics['period']
			period_count = req_metrics['period_count']
			period_count_add = req_metrics['period_count_add']
			period_duration = req_metrics['period_duration']

			period_is_actual = True if period + period_duration > tm else False

			if period_is_actual:
				if period_count + period_count_add == period_count_max:
					return 0
				elif period_count == period_count_max:
					return 0
				elif period_count + period_count_add < period_count_max:
					pass

			else:
				if period_count + period_count_add == period_count_max:
					return 0
				elif period_count_add < period_count_max:
					pass

		number_max = req_metrics.get('number_max')
		if number_max:
			# maximum_at_a_time=req_metrics['maximum_at_a_time']
			number = req_metrics['number']
			number_add = req_metrics['number_add']
			if number + number_add == number_max:
				return 0
			else:
				return_number = number_max - number - number_add

		maximum_at_a_time = req_metrics.get('maximum_at_a_time')
		if maximum_at_a_time:
			if return_number:
				return_number = min(maximum_at_a_time, return_number)
			else:
				return_number = maximum_at_a_time
		if return_number:
			return return_number
		else:
			return default_number

	###
	##
	#
	# {REPORT_INTERFACE}
	##{MNGR_LEVEL}
	def report_sub(self, tracks_map):
		self.on_sending_update_metrics_sub(len(tracks_map))
		for stream_id, track_id in tracks_map.items():
			self.streams_map[track_id] = stream_id
			self.tracks_map[stream_id] = track_id

	def report_clousing(self):
		self.to_be_closed = True

	def report_unsub(self, stream_ids):
		stream_ids = stream_ids if isinstance(stream_ids, list) else [stream_ids]
		self.on_sending_update_metrics_unsub(len(stream_ids))

	def report_stream_closed(self, stream_id):
		track_id = self.tracks_map.pop(stream_id)
		self.streams_map.pop(track_id)

	##

	##{CONNECTION_LEVEL}
	def report(self, msg):
		getattr(self, 'on_%s' % msg['tp'])(msg)

	###{INTERNAL}
	def on_report(self, msg):
		getattr(self, 'on_report_%s' % msg['report_tp'])(msg)

	def on_report_open(self, msg):
		self.to_connected_state(msg)

	def on_report_send(self, msg):
		pass

	def on_report_send_failed(self, msg):
		self.on_send_failed_update_metrics(None)

	def on_report_close(self, msg):

		self.to_closed_state(msg)

	def on_success(self, msg):
		self.external_msg_received(msg['tm'])
		self.on_success_update_metrics_sub(len(msg['track_ids']))

	def on_conflict(self, msg):
		self.on_conflict_update_metrics_sub(len(msg['track_ids']))

	def on_unsub(self, msg):

		self.external_msg_received(msg['tm'])
		self.on_success_update_metrics_unsub(len(msg['track_ids']))

	def on_get(self, msg):
		pass

	def on_conflict_get(self, msg):
		pass

	def on_failure(self, msg):
		# self.external_msg_received(msg['tm'])
		self.to_closed_state(msg)
		
	def on_conn_error(self, msg):
		#print(msg)
		self.to_closed_state(msg)

	def on_connection_error(self, msg):
		'''
		gaierror(-3, 'Temporary failure in name resolution')
		получается при попытке открыть соендинение без подключения к интернету
		'''
		self.to_closed_state(msg)

	def on_greeting(self, msg):
		self.external_msg_received(msg['tm'])
		if self.state != 'active':
			self.to_active_state(msg)

	def on_data(self, msg):
		self.external_msg_received(msg['tm'])
		if self.state != 'active':
			self.to_active_state(msg)

	def on_pong(self, msg):
		self.external_msg_received(msg['tm'])
		if self.state != 'active':
			self.to_active_state(msg)

	####{INTERNAL}
	def external_msg_received(self, tm):
		tm = to_s(tm)
		silence_sd = tm - self.external_msg_tm
		self.external_msg_tm = tm
		self.max_silence_sd = max(self.max_silence_sd, silence_sd)

	#####
	###
	##
	#
	# {STATE_UPDATE_METHODS}
	def to_created_state(self, msg=None):
		self.state_past = None
		self.state = 'created'
		self.max_silence_sd = 0

		self.deadline = None
		self.external_msg_tm = time_ms()
		self.update_tm = time_ms()

		tm_s = time_s()
		self.on_created_update_metrics_connections(tm_s)

	def to_connecting_state(self, msg):
		self.state_past = self.state
		self.state = 'connecting'
		self.update_tm = msg['tm']

		tm_s = to_s(msg['tm'])
		self.on_connecting_update_metrics_connections(tm_s)

	def to_connected_state(self, msg):
		self.state_past = self.state
		self.state = 'connected'
		self.update_tm = msg['tm']
		self.deadline = to_s(msg['tm']) + self.deadline_sd
		self.update_tm = to_s(msg['tm'])

		tm_s = to_s(msg['tm'])
		self.on_connected_update_metrics_connections(tm_s)

	def to_active_state(self, msg):
		self.state_past = self.state
		self.state = 'active'
		self.update_tm = msg['tm']

		tm_s = to_s(msg['tm'])
		self.on_active_update_metrics_connections(tm_s)

	def to_closed_state(self, msg):

		self.state_past = self.state
		self.state = 'closed'
		if msg['tp'] == 'report':
			self.reason = 'ok'
			self.about_reason = None
		elif msg['tp'] == 'failure':
			self.reason = 'failure'
			self.about_reason = msg
		elif msg['tp'] == 'conn_error':
			self.reason = 'conn_error'
			self.about_reason = msg

		tm_s = to_s(msg['tm'])
		self.on_closed_update_metrics_connections(tm_s)

	#
	# {METRICS_CONNECTIONS_UPDATE_METHODS}
	def on_created_update_metrics_connections(self, tm=None):
		self.metrics_connections['number'] += 1

	def on_connecting_update_metrics_connections(self, tm):
		period_count_max = self.metrics_connections['period_count_max']
		period = self.metrics_connections['period']
		period_count = self.metrics_connections['period_count']
		period_count_add = self.metrics_connections['period_count_add']
		period_duration = self.metrics_connections['period_duration']
		period_is_actual = True if period + period_duration > tm else False

		if not period_count_add:
			if (period_is_actual and not period_count) or not period_is_actual:
				self.metrics_connections['period'] = tm
				self.metrics_connections['period_count'] = 0

		self.metrics_connections['period_count_add'] += 1

	def on_connected_update_metrics_connections(self, tm):
		mc=self.metrics_connections
		tm=time_s()
		
		period_is_actual=mc['period']+mc['period_duration']>tm
		
		if (period_is_actual and not mc['period_count']) or not period_is_actual:
			mc['period']=tm
			mc['period_count']=0
		mc['period_count_add']-=1
		mc['period_count']+=1

	def on_active_update_metrics_connections(self, tm):
		pass

	def on_closed_update_metrics_connections(self, tm):
		if self.state_past == 'connecting':
			self.on_connected_update_metrics_connections(tm)
		self.metrics_connections['number'] -= 1

	#
	# {METRICS_REQUESTS_UPDATE_METHODS}
	'''
	имеют базу для обобщения но ее не используют, в пол6ой мере.
	'''

	def on_sending_update_metrics_sub(self, lenght):
		tm = time_s()
		sub_metrics = self.metrics_requests['sub']
		sub_metrics['number_add'] += lenght

		base_metrics = self.metrics_requests[sub_metrics['base']]

		period_count_max = base_metrics.get('period_count_max')
		period = base_metrics['period']
		period_count = base_metrics['period_count']
		period_count_add = base_metrics['period_count_add']
		period_duration = base_metrics['period_duration']

		period_is_actual = True if period + period_duration > tm else False

		if period_is_actual:
			if period_count_add:
				base_metrics['period_count_add'] += 1
			else:
				base_metrics['period_count_add'] = 1
		else:
			if period_count_add:
				base_metrics['period_count_add'] += 1
			if not period_count_add:
				base_metrics['period'] = tm
				base_metrics['period_count'] = 0
				base_metrics['period_count_add'] = 1

		{
			'sub': {
				'base': 'msg',
				'maximum_at_a_time': 25,
				'number': 0,
				'number_add': 0,
				'number_max': 50,

			},
			'msg': {
				'period': time_s(),
				'period_count': 0,
				'period_count_add': 0,
				'period_count_max': 3,
				'period_duration': td_to_sd('1s')
			},
			'unsub': None,  # нет лимитов
			'get': None
		}

	def on_sended_update_metrics_sub(self, lenght):
		pass

	def on_success_update_metrics_sub(self, lenght):
		tm = time_s()
		sub_metrics = self.metrics_requests['sub']
		sub_metrics['number_add'] -= lenght
		sub_metrics['number'] += lenght

		base_metrics = self.metrics_requests[sub_metrics['base']]

		period_count_max = base_metrics.get('period_count_max')
		period = base_metrics['period']
		period_count = base_metrics['period_count']
		period_count_add = base_metrics['period_count_add']
		period_duration = base_metrics['period_duration']

		period_is_actual = True if period + period_duration > tm else False

		if period_is_actual:
			if not period_count:
				base_metrics['period'] = tm
			base_metrics['period_count'] += 1
			base_metrics['period_count_add'] -= 1

		else:
			base_metrics['period'] = tm
			base_metrics['period_count'] = 0
			base_metrics['period_count'] += 1
			base_metrics['period_count_add'] -= 1

	def on_conflict_update_metrics_sub(self, lenght):
		tm = time_s()
		sub_metrics = self.metrics_requests['sub']
		sub_metrics['number_add'] -= lenght

	def on_send_failed_update_metrics(self, lenght=None):
		self.metrics_requests['msg']['period_count_add'] -= 1

	def on_sending_update_metrics_unsub(self, lenght):
		pass

	def on_success_update_metrics_unsub(self, lenght):
		sub_metrics = self.metrics_requests['sub']
		sub_metrics['number'] -= lenght


#
# [END:Connection_info]


# [BEGIN:Connection_mngr]
class Connections_mngr:
	unreliable_td = '5m'
	deadline_td = '24h'
	retire_td = '12h'
	silence_td = '2m'
	max_silence_td = '3m'

	limits = {  # union
		'msg': {
			'per_period': 3,
			'period_duration': '1s',
			'coverage': 'local',
			'sub': {
				'max_per_msg': 25,
				'max': 50
			}
		},
		'unsub': {
			'per_period': None,
			'period_duration': None
		}
	}
	limits_conn = {  # union
		'per_period': 2,
		'period_duration': '1s',
		'max': 200
	}

	# {CONTROL_INTERFACE}
	def __init__(self, stream_callback):
		self.stream_callback = stream_callback
		self.connections = {}
		self.connections_info = {}
		self.connecting_tasks = {}
		self.pendings_streams = []
		self.pendings_streams_delay = []
		self.distribution_streams_task = None

		self.metrics_connections = self.get_metrics_connections()
		self.metrics_requests_global = self.get_metrics_requests_global()

	##{INTERNAL}
	def get_metrics_connections(self):  # union
		metrics_connections = {
			'period': time_s(),
			'period_count': 0,
			'period_count_add': 0,
			'number': 0,
			'number_max': self.limits_conn['max'],
			'period_duration': td_to_sd(self.limits_conn['period_duration']),
			'period_count_max': self.limits_conn['per_period']
		}
		return metrics_connections

	def get_metrics_requests_global(self):  # union
		return {}

	def get_metrics_requests_local(self):  # union
		metrics_requests = {
			'sub': {
				'base': 'msg',
				'maximum_at_a_time': 25,
				'number': 0,
				'number_add': 0,
				'number_max': 50,

			},
			'msg': {
				'period': time_s(),
				'period_count': 0,
				'period_count_add': 0,
				'period_count_max': 3,
				'period_duration': td_to_sd('1s')
			},
			'unsub': {
				'maximum_at_a_time': 25,
			},  # нет лимитов
			'get': None
		}
		return metrics_requests

	##

	def close(self):
		for conn_id, connection_info in self.connections_info.items():
			self.close_connection(conn_id)

	#
	# {CONNECTIONS_CONTROL_INTERFACE}
	async def add_connection(self, timeout=None):
		tm1 = time_s()
		tm2 = time_s()
		while True:
			if tm2 - tm1 >= timeout:
				raise TimeoutError
			if self.connect_allowed() and self.create_allowed():
				conn_id = self.create_connection()
				self.connect_connection_nowait(conn_id)
			else:
				await asyncio.sleep(td_to_sd(self.limits_conn['period_duration']))
			tm2 = time_s()
		return conn_id

	def add_connection_nowait(self):
		if self.create_allowed():
			conn_id = self.create_connection()
			self.connect_connection_nowait(conn_id)

	def create_connection(self):
		if not self.create_allowed():
			raise CreateNotAllowed
		conn_id = self.assign_id()
		callback = self.wrap_callback(conn_id)
		connection = Connection_ws(callback)
		self.connections[conn_id] = connection

		metrics_requests_local = self.get_metrics_requests_local()
		connection_info = Connection_info(
			metrics_requests_local,
			self.metrics_requests_global,
			self.metrics_connections,

			deadline_td=self.deadline_td,
			retire_td=self.retire_td,
			silence_td=self.silence_td,
			unreliable_td=self.unreliable_td

		)

		self.connections_info[conn_id] = connection_info
		return conn_id

	async def connect_connection(self, conn_id):
		while True:
			if not self.connect_allowed():
				await asyncio.sleep(td_to_sd(self.limits_conn['period_duration']))
				continue

			self.connections_info[conn_id].to_connecting_state({'tm': time_ms()})

			await self.connections[conn_id].open()

			if self.connecting_tasks.get(conn_id):
				self.connecting_tasks.pop(conn_id)
			break

	def connect_connection_nowait(self, conn_id):
		self.connecting_tasks[conn_id] = asyncio.create_task(self.connect_connection(conn_id))

	def close_connection(self, conn_id):

		connection_info = self.connections_info[conn_id]
		stream_ids = []
		for track_id, stream_id in connection_info.streams_map.items():
			stream_ids.append(stream_id)
		

		asyncio.create_task(self.connections[conn_id].close())

		connection_info.report_clousing()

		msg = {
			'tp': 'report',
			'report_tp': 'closed',
			'tm': time_ms()
		}

		for stream_id in stream_ids:
			connection_info.report_stream_closed(stream_id)
			self.callback(msg, stream_id)

	def prepare_connections(self):
		required_space = len(self.pendings_streams) + len(self.pendings_streams_delay)
		freespace_sum = self.allowed_number_sub_residue_all_usable()
		missing_space = required_space - freespace_sum

		if missing_space > 0:
			required_conns = (missing_space + 50 - 1) // 50 + 1
			for i in range(required_conns):
				self.add_connection_nowait()
		else:

			pendings_all = [*self.pendings_streams_delay, *self.pendings_streams]

			request_used_connections = {}
			request_delayed_lenght = {}

			for stream in pendings_all:
				if not request_delayed_lenght.get(stream.request.id):
					request_delayed_lenght[stream.request.id] = 0
					request_used_connections[stream.request.id] = stream.request.used_connections
				request_delayed_lenght[stream.request.id] += 1
			min_additional_conns = 0

			# all_subable_connections:
			# 1. не закрытыеб не молчащие не устаревшие, с доступными лимитами по подпискам

			subable_connections = self.get_subable_connections_all()
			for request_id, delayed_lenght in request_delayed_lenght.items():
				connections_for_delayed = list(set(subable_connections) - set(request_used_connections[request_id]))
				min_additional_conns = max(min_additional_conns, delayed_lenght - len(connections_for_delayed))

			for i in range(min_additional_conns):
				self.add_connection_nowait()

	##{INTERNAL}
	def wrap_callback(self, conn_id):
		def wrapped_callback(msg, conn_id=conn_id):
			try:
				# if msg['tp']!='data':

				connection_info = self.connections_info[conn_id]

				if connection_info.is_closed():
					return

				connection_info.report(msg)

				# if connection_info.state=='connected':
				#	self.connecting_tasks.pop(conn_id)


				if msg.get('track_id'):
					stream_id = connection_info.streams_map.get(msg['track_id'])
					if stream_id:
						self.stream_callback(msg, stream_id)

				elif msg.get('track_ids'):
					for track_id in msg['track_ids']:
						stream_id = connection_info.streams_map.get(track_id)
						if stream_id:
							self.stream_callback(msg, stream_id)



				if connection_info.is_closed():

					msg = {
						'tp': 'connection_closed',
						'reason': connection_info.reason,
						'about_reason': connection_info.about_reason,
						'tm': msg['tm']
					}
					

					for stream_id in list(connection_info.streams_map.values()):
						self.stream_callback(msg, stream_id)
						
						
					self.connections_info.pop(conn_id)
					self.connections.pop(conn_id)


				# self.stream_callback(msg, stream_id)

				f = asyncio.Future()
				f.set_result(1)
				return f
			except Exception as E:
				self.eee = E

		return wrapped_callback

	def assign_id(self):
		if not hasattr(self, 'last_id'):
			self.last_id = 0
		self.last_id += 1
		return self.last_id

	##
	#
	# {INFO_INTERFACE}
	##{CONNECTIONS_LIMITS_INFO}
	def create_allowed(self):
		"""
		return: True if max number of connetions not is reached
			False if max number of connections is reached.
		"""
		if self.metrics_connections['number'] == self.limits_conn['max']:
			return False
		else:
			return True

	def connect_allowed(self):	
		mc=self.metrics_connections
		tm=time_s()
		period_is_actual=mc['period']+mc['period_duration']>tm
		
		if period_is_actual:
			if mc['period_count_add']+mc['period_count']==mc['period_count_max']:
				return False
		else:
			if mc['period_count_add']==mc['period_count_max']:
				return False
		return True

			
				

	##
	##{REQUESTS_LIMITS_INFO}
	def allowed_number_sub(self, conn_id):
		return self.connections_info[conn_id].allowed_number_sub()

	def allowed_number_get(self, conn_id):
		return self.connections_info[conn_id].allowed_number_get()

	def allowed_number_unsub(self, conn_id):
		return self.connections_info[conn_id].allowed_number_get()

	def allowed_number_sub_residue(self, conn_id):
		return self.connections_info[conn_id].allowed_number_sub_residue()

	def allowed_number_sub_residue_all(self):
		sum_freespace = 0
		for conn_id, connection_info in self.connections_info.items():
			sum_freespace += connection_info.allowed_number_sub_residue()
		return sum_freespace

	def allowed_number_sub_residue_all_usable(self):
		sum_freespace = 0
		for conn_id, connection_info in self.connections_info.items():
			if connection_info.is_ok():
				sum_freespace += connection_info.allowed_number_sub_residue()
		return sum_freespace

	def get_subable_connections_now(self):
		subable_connections = []
		for conn_id, connection_info in self.connections_info.items():
			if connection_info.is_ok() and connection_info.is_active() and connection_info.allowed_number_sub():
				subable_connections.append(conn_id)
		return subable_connections

	def get_subable_connections_all(self):
		subable_connections = []
		for conn_id, connection_info in self.connections_info.items():
			if connection_info.is_ok() and connection_info.allowed_number_sub_residue():
				subable_connections.append(conn_id)
		return subable_connections

	##
	#
	# {STREAMS_CONTROL_INTERFACE}
	def add_stream(self, stream):
		if stream.start_is_delayed():
			self.pendings_streams_delay.append(stream)
		else:
			self.pendings_streams.append(stream)

		if not self.distribution_streams_task or self.distribution_streams_task.done():
			self.distribution_streams_task = asyncio.create_task(self.distribute_streams())

	def close_streams(self, stream_s):
		streams = stream_s if isinstance(stream_s, list) else [stream_s]
		# streams_by_conns = {}
		for stream in streams:
			self.close_stream(stream)

	def close_stream(self, stream):
		conn_id = stream.conn_id
		if not conn_id:
			if stream in self.pendings_streams:
				self.pendings_streams.remove(stream)
			elif stream in self.pendings_streams_delay:
				self.pendings_streams_delay.remove(stream)
			return
		track_id = self.connections_info[conn_id].tracks_map.get(stream.id)
		self.connections_info[conn_id].report_stream_closed(stream.id)
		if self.connections[conn_id].is_served(track_id):

			self.connections[conn_id].unsub(track_id)
		if self.connections_info[conn_id].is_empty():
			self.close_connection(conn_id)


	##{INTERNAL}
	async def distribute_streams(self):
		try:
			while self.pendings_streams:
				self.prepare_connections()
				awailable_connections = self.get_subable_connections_now()
				for conn_id in awailable_connections:
					freespace = self.allowed_number_sub(conn_id)
					sendings_indices = []
					for i, stream in enumerate(self.pendings_streams):
						if conn_id in stream.get_exclude_connections():
							continue
						sendings_indices.append(i)
						freespace -= 1
						if not freespace:
							break
					if not sendings_indices:
						continue
					else:
						sendings = [self.pendings_streams.pop(i) for i in reversed(sendings_indices)]
						break
				else:
					await asyncio.sleep(0.5)
					continue
				self.add_streams_to_connection(conn_id, sendings)

				for stream in sendings:
					if not self.pendings_streams_delay:
						break
					delayed_streams = stream.request.get_pendings_streams()
					for stream in delayed_streams:
						if stream in self.pendings_streams_delay:
							self.pendings_streams.append(stream)
							self.pendings_streams_delay.remove(stream)
							break
						else:
							raise Exception('такого происходить не должно.')
		except Exception as E:
			self.eee = E

	def add_streams_to_connection(self, conn_id, streams):
		try:
			streams_params = []
			for stream in streams:
				params = stream.request.params
				params['return_label'] = stream.id
				streams_params.append(params)

			tracks = self.connections[conn_id].req_low_nowait(streams_params)
			tracks_map = {}
			for track in tracks:
				tracks_map[track['return_label']] = track['track_id']

			self.connections_info[conn_id].report_sub(tracks_map)

			msg = {
				'tp': 'report',
				'report_tp': 'sending',
				'conn_id': conn_id,
				'deadline': self.connections_info[conn_id].deadline,
				'tm': time_ms()
			}

			for stream_id in tracks_map.keys():
				self.stream_callback(msg, stream_id)
		except Exception as E:
			self.eee = E


	def is_closed(self):

		return self.metrics_connections['number']==0

##
#
# [END:Connection_mngr]


class Request:
	id_seq = sequence(1)
	requests_map = {}
	requests = {}

	# {GLOBAL_INTERFACE}
	def clear(requests_map=requests_map, requests=requests):
		requests_map.clear()
		requests.clear()

	def find_request(request_params, requests_map=requests_map):
		request_params_tuple = tuple([value for value in request_params.values()])
		return requests_map.get(request_params_tuple)

	def get_request(request_id, requests=requests):
		return requests.get(request_id)

	def connection_closed(conn_id, requests=requests):
		for request in requests.values():
			request.connection_closed(conn_id)

	#
	# {CONTROL_INTERFACE}
	def __init__(self, params):
		self.params = params

		request_params_tuple = tuple([value for value in params.values()])
		self.requests_map[request_params_tuple] = self

		self.id = next(self.id_seq)
		self.requests[self.id] = self

		self.params = params
		self.used_connections = []
		self.streams = {}

	def stream_added(self, stream):
		self.streams[stream.id] = stream

	def stream_closed(self, stream):
		self.streams.pop(stream.id)

	def connection_closed(self, conn_id):
		if conn_id in self.used_connections:
			self.used_connections.remove(conn_id)

	def connection_use(self, conn_id):
		self.used_connections.append(conn_id)

	def get_pendings_streams(self):
		pendings = []
		for stream_id, stream in self.streams.items():
			if stream.state == 'pending':
				pendings.append(stream)
		return pendings

#


class Stream:
	id_seq = sequence(1)

	def __init__(self, request, callback, start_method, close_method, ignore=None):
		self.request = request
		self.callback = callback
		self.ignore = ignore if ignore else []
		self.id = next(self.id_seq)
		self.start = self.start_wrapper(start_method)
		self.close = self.close_wrapper(close_method)

		self.state = None
		self.to_pending_state({'tp': 'add_stream', 'tm': time_ms()}, False)

	# {CONTROL_INTERFACE}
	def start_wrapper(self, start_method):
		def wrapped():
			self.request.stream_added(self)
			return start_method(self)

		return wrapped

	def close_wrapper(self, close_method):
		def wrapped():
			self.request.stream_closed(self)
			return close_method(self)

		return wrapped

	def restart(self):
		self.close()
		self.to_pending_state({'tp': 'restart', 'tm': time_ms()}, False)
		self.start()

	#
	# {INFO_INTERFACE}
	def start_is_delayed(self):
		for stream_id_other, stream_other in self.request.streams.items():
			if stream_id_other == self.id:
				continue
			if not stream_other.conn_id:
				return True
		return False

	def get_exclude_connections(self):
		return self.request.used_connections

	#
	# {REPORT_INTERFACE}
	def report(self, msg):
		getattr(self, 'on_%s' % msg['tp'])(msg)
		
	def on_connection_closed(self, msg):

		self.on_conn_closed(msg)

	def on_report(self, msg):
		getattr(self, 'on_report_%s' % msg['report_tp'])(msg)

	def on_report_sending(self, msg):
		self.to_sending_state(msg)

	def on_report_send(self, msg):
		self.to_sended_state(msg)

	def on_success(self, msg):
		self.to_success_state(msg)

	def on_report_closed(self, msg):
		self.on_conn_closed(msg)

	def on_failure(self, msg):
		self.on_conn_closed(msg)

	def on_conn_error(self, msg):
		self.on_conn_closed(msg)

	def on_conn_closed(self, msg):  # report.closed, failure, conn_error
		self.to_pending_state(msg)
		self.close()
		self.start()

	def on_conflict(self, msg):
		self.request.connection_use(self.conn_id)
		self.restart(msg)

	def on_unsub_success(self, msg):
		'''
		никогда не получает.
		'''
		pass

	def on_report_unsub(self, msg):
		'''
		никогда не получает.
		'''
		pass

	def on_action_unsub(self, msg):
		'''
		никогда не получает.
		'''
		pass

	def on_data(self, msg):
		if self.state != 'active':
			self.to_active_state(msg)
		self.data_tm = msg['tm']
		self.callback(self.get_data_msg(msg))

	def get_data_msg(self, msg):
		data_tp = msg['data_tp']
		data = msg[data_tp]
		msg = {
			'tp': 'data',
			'data': data,
			'stream_id': self.id,
			'request_id': self.request.id,
			'tm': msg['tm']
		}
		return msg

	#
	# {STATE_UPDATE_METHODS}
	def to_pending_state(self, msg, feedback=True):
		self.state_past = self.state
		self.state = 'pending'
		self.update_tm = msg['tm']
		self.reason = msg['tp']
		self.about_reason = msg
		self.conn_id = None
		self.deadline = None
		self.data_tm = None
		if feedback:
			self.state_updated()

	def to_sending_state(self, msg, feedback=True):
		self.state_past = self.state
		self.state = 'sending'
		self.update_tm = msg['tm']
		self.reason = None
		self.about_reason = None
		self.conn_id = msg['conn_id']
		self.deadline = msg['deadline']
		self.request.connection_use(self.conn_id)

		self.deadline = msg['deadline']
		if feedback:
			self.state_updated()

	def to_sended_state(self, msg, feedback=True):
		self.state_past = self.state
		self.state = 'sended'
		self.update_tm = msg['tm']
		if feedback:
			self.state_updated()

	def to_success_state(self, msg, feedback=True):
		self.state_past = self.state
		self.state = 'success'
		self.update_tm = msg['tm']
		if feedback:
			self.state_updated()

	def to_active_state(self, msg, feedback=True):
		self.state_past = self.state
		self.state = 'active'
		self.update_tm = msg['tm']
		if feedback:
			self.state_updated()

	def state_updated(self):
		if self.state not in self.ignore:
			self.callback(self.get_state_msg())

	def get_state_msg(self):
		state_msg = {
			'tp': 'stream_state',
			'stream_id': self.id,
			'state': self.state,
			'state_past': self.state_past,
			'reason': self.reason,
			'about_reason': self.about_reason,
			'conn_id': self.conn_id,
			'deadline': self.deadline,
			'request_id': self.request.id,
			'update_tm': self.update_tm,
			'data_tm': self.data_tm
		}

		# for key in list(state_msg.keys()):
		#	if state_msg[key] is None:
		#		state_msg.pop(key)
		return state_msg


#


class Interface_ws:

	def __init__(self):
		self.connections_mngr = Connections_mngr(self.stream_callback)
		self.streams = {}

	# {MAIN_INTERFACE}
	##{HIGH_LEVEL}
	def sub_ohlcv_up(self, market, interval='1m', callback=None, ignore=None):
		requests_params = {'req_tp': 'sub', 'data_tp': 'ohlcv_up', 'market': market, 'interval': interval}
		request_id = self.add_request(requests_params)
		stream_id = self.add_stream(request_id, callback, ignore)
		return stream_id

	def sub_ohlcv_up_multi(self, markets, interval, callback, ignore=None):
		stream_ids = []
		for market in markets:
			stream_id = self.sub_ohlcv_up(market, interval, callback, ignore)
			stream_ids.append(stream_id)
		return stream_ids


	
	def sub_trades_up(self, market, callback, ignore=None):
		request_params={'req_tp':'sub', 'data_tp':'trades_up', 'market':market}
		request_id = self.add_request(request_params)
		stream_id = self.add_stream(request_id, callback, ignore)
		return stream_id
	
	def sub_tickers_C(self, market):
		pass
	
	def sub_tickers_CHL(self, market):
		pass
		
	
	def sub_orderbook_up(self, market, frequency=100, callback=None, ignore=None):
		request_params={'req_tp':'sub', 'data_tp':'orderbook_up', 'market':market, 'frequency':frequency}
		request_id = self.add_request(request_params)
		stream_id = self.add_stream(request_id, callback, ignore)
		return stream_id
	

	##
	##{LOW_LEVEL}
	def add_request(self, request_params):
		request = Request.find_request(request_params)
		if not request:
			request = Request(request_params)
		return request.id

	def add_stream(self, request_id, callback, ignore=None):
		request = Request.get_request(request_id)
		stream = Stream(request,
						callback,
						self.connections_mngr.add_stream,
						self.connections_mngr.close_streams,
						ignore)
		self.streams[stream.id] = stream
		stream.start()
		return stream.id

	def close_streams(self, stream_ids):
		for stream_id in stream_ids:
			self.close_stream(stream_id)

	def close_stream(self, stream_id):
		self.streams[stream_id].close()
		del self.streams[stream_id]

	# self.streams[stream_id].dont_restart()
	# self.stream[stream_id].close()

	def restart_streams(self, stream_ids):
		for stream_id in stream_ids:
			self.restart_stream(stream_id)

	def restart_stream(self, stream_id):
		self.streams[stream_id].restart()

	async def reboot(self):
		self.close_streams(list(self.streams.keys()))
		self.connections_mngr.close()
		while not self.connections_mngr.is_closed():
			await asyncio.sleep(0.2)
		Request.clear()
		self.__init__()
		
	##
	#
	# {INTERNAL}
	def stream_callback(self, msg, stream_id):
		self.streams[stream_id].report(msg)


	"""
	def get_result(self, request_id, callback=None, timeout=None):
		ignore=['pending', 'sending', 'sended', 'success']
		request=Request.get_request(request_id)
		future_return=False
		if not callback:
			future_return=True
			future=asyncio.Future()
			callback=future.set_result
			wrapped_callback=self.wrap_get_callback(callback)


		stream=Stream(request, self.start_stream, self.close_stream, wrapped_callback, ignore)

		if future_return:
			return future
		else
			return stream.id


	def wrap_get_callback(self, callback):
		def wrapped(msg):
			self.streams.close(msg['stream_id'])
			callback(msg)

		return wrapped

	"""

