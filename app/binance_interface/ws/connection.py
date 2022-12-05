import asyncio
import websockets
import json
import random
from copy import deepcopy as copy
from inspect import iscoroutinefunction
import numpy as np


from time_funcs import *
import dict_funcs
from binance_interface.ws.connection_exceptions import *


def connect_deco(method):
	async def connect_wrapper(self, *args, **kwargs):
		if self.connected or self.closed:
			raise Exception('method "connect" has already been used')

		await method(self, *args, **kwargs)

		self.connected = True

	# await self.callback({'tp': 'open', 'data': None, 'tm': time_ms()})

	return connect_wrapper


def disconnect_deco(method):
	async def disconnect_wrapper(self, *args, **kwargs):
		if self.closed:
			raise Exception('connection already closed')
		self.closed = True
		await method(self, *args, **kwargs)

	# await self.callback({'tp': 'close', 'data': None, 'tm': time_ms()})

	return disconnect_wrapper


def low_deco(method):
	async def wrapper(self, *args, **kwargs):
		requests_params = await method(self, *args, **kwargs)
		return await self.req_low(requests_params)

	return wrapper


def as_async(func):
	async def wrapper(*args, **kwargs):
		return func(*args, **kwargs)
	return wrapper
	
class Connection:
	connect_params = {}

	def __init__(self, callback, do_not_return=None, auto_connect=False, connect_params=None):
		"""
		callback:coroutine
		auto_connect:bool	//True - calling the "connect" method is not required, at the start of requests, "connect" will be called automatically,
					//False - call "connect" is required
		auto_disconect		//??

		"""
		#if not iscoroutinefunction(callback):
		#	raise Exception('callback must be a coroutine')

		self.closed = False  #
		self.active = False  #
		self.connected = False  # метод connect уе был вызван
		self.conn = None
		
		if iscoroutinefunction(callback):
			self.callback=callback
		else:
			self.callback=as_async(callback)
	
	
		self.do_not_return = (do_not_return if isinstance(do_not_return, list) else [do_not_return]) if do_not_return else []

		self.auto_connect = auto_connect
		# self.auto_disconect = auto_disconnect

		self.connect_params = copy(self.connect_params)
		if connect_params:
			for key, value in connect_params.items():
				self.connect_params[key] = value

		self.__init_children__()

		self.symbols_map = {}

		self.track_id_last = 0

	def __initsub__(self):
		pass

	# self.handle=self.async_executor.get_tasks_interface(self.parser.parse)

	# {CONNECTION_CONTROL_INTERFACE}

	@connect_deco
	async def connect(self, **connect_params):
		raise NotImplementedError

	@disconnect_deco
	async def disconnect(self):
		raise NotImplementedError

	def is_ready(self):
		"""
		1.готово ли соендиение к подпискам
		"""
		return self.is_connected() and not self.closed

	def is_active(self):
		"""
		1.готово ли соендиение к подпискам(частный случай is_ready), но в отличии от is_ready еще показывает, что соендинение фактически функционирует
		"""
		if self.active:
			return True

	def is_connected(self):
		"""
		1.показывает надобность в connect
		"""
		return self.connected or self.auto_connect

	def is_closed(self):
		"""
		1. показывает что соендинение не было сброшенно
		"""
		return self.closed

	##{INTERNAL}
	def get_adress(self, **params):
		return self.url

	def decode(self, raw):
		raise NotImplementedError

	# def parse(self, msg):
	#   return self.parser.parse(msg)

	# async def handle(self, raw):
	#	try:
	#		decoded=self.decode(msg)
	#	except:

	# def handle(self, raw):
	#	decoded = self.decode(msg)
	#   parsed = self.parsed(decoded)
	#	return parsed

	# def parse(self, msg):
	#	raise NotImplementedError

	# await def run(self):
	#	raise NotImplementedError

	#

	# {REQUESTS_INTERFACE}
	##{LOW}
	async def req_low(self, requests_params):
		"""
		requests_params:[
			{'req_tp':str, 'data_tp':str, 'market'"none|str, **params}

		"""

		if self.closed:
			raise Exception('the connection was closed')
		if not self.connected:
			if not self.auto_connect:
				raise Exception('connection not yet open')
			else:
				await self.connect(self.connect_params)

		if isinstance(requests_params, dict):
			track_id = self.assign_track_id()
			for_tracking = {
				**requests_params,
				'track_id': track_id
			}
			requests_params['track_id'] = track_id
			requests_params = [requests_params]

		elif isinstance(requests_params, list):
			for_tracking = []
			for request_params in requests_params:
				track_id = self.assign_track_id()
				for_tracking.append({
					**request_params,
					'track_id': track_id
				})
				request_params['track_id'] = track_id

		requests_commands = self.get_requests_commands(requests_params)
		#print(requests_commands)
		for command in requests_commands:
			await self.send(command)

		return for_tracking

	def req_low_nowait(self, requests_params):
		"""
		requests_params:[
			{'req_tp':str, 'data_tp':str, 'market'"none|str, **params}

		"""
		requests_params=copy(requests_params)

		if self.closed:
			raise Exception('the connection was closed')
		if not self.connected:
			raise Exception('connection not yet open')

		if isinstance(requests_params, dict):
			track_id = self.assign_track_id()
			for_tracking = {
				**requests_params,
				'track_id': track_id
			}
			requests_params['track_id'] = track_id
			requests_params = [requests_params]

		elif isinstance(requests_params, list):
			for_tracking = []
			for request_params in requests_params:
				track_id = self.assign_track_id()
				for_tracking.append({
					**request_params,
					'track_id': track_id
				})
				request_params['track_id'] = track_id

		requests_commands = self.get_requests_commands(requests_params)
		#print(requests_commands)
		if not requests_commands:
			msg={
				'tp':'report',
				'report_tp':'send_failed',
				'tm':time_ms()
			}
			self.schedule_later(self.callback, msg)
			
		for command in requests_commands:
			asyncio.create_task(self.send(command))

		return for_tracking

	def assign_track_id(self, track_id_external=None):
		self.track_id_last += 1
		return self.track_id_last

	def get_requests_commands(self, requests_params):
		raise NotImplementedError

	async def send(self, request):
		raise NotImplementedError

	##
	##{HIGH}
	"""
	так как sub это update то можно наверно не приписывать up к п\методам sub
	"""

	@low_deco
	async def req_data_tp(self, market_s, **params):
		"""
		market_s:str or list	//
		**params:ANY		//see connection.templates[data_tp][req_tp]['order']
		return:dict or list	//extended request description with track_id for tracking:
					//	for one market:
					//		{'track_id':int, 'req_tp':req_tp, 'data_tp':data_tp, 'market':market, **params}
					//	for markets list:
					//		[
					//			{'track_id':int, 'req_tp':req_tp, 'data_tp':data_tp, 'market':market_1, **params},
					//			...
					//			{'track_id':int, 'req_tp':req_tp, 'data_tp':data_tp, 'market':market_n, **params}
					//		]

		"""
		raise Exception('doc method')

	@low_deco
	async def get_orderbook(self, market_s, **params):
		return self.get_requests_params('get', 'orderbook', True, market_s, **params)

	@low_deco
	async def sub_orderbook_up(self, market_s, **params):
		return self.get_requests_params('sub', 'orderbook_up', True, market_s, **params)

	@low_deco
	async def get_trades(self, market_s, **params):
		return self.get_requests_params('get', 'trades', True, market_s, **params)

	@low_deco
	async def sub_trades_up(self, market_s, **params):
		return self.get_requests_params('sub', 'trades_up', True, market_s, **params)

	@low_deco
	async def get_tickers_C(self, market_s=None, **params):
		return self.get_requests_params('get', 'tickers_C', False, market_s, **params)

	@low_deco
	async def sub_tickers_C(self, market_s=None, **params):
		return self.get_requests_params('sub', 'tickers_C', False, market_s, **params)

	@low_deco
	async def get_tickers_CHL(self, market_s=None, **params):
		return self.get_requests_params('get', 'tickers_CHL', False, market_s, **params)

	@low_deco
	async def sub_tickers_CHL(self, market_s=None, **params):
		return self.get_requests_params('sub', 'tickers_CHL', False, market_s, **params)

	@low_deco
	async def get_ohlcv(self, market_s, **params):
		return self.get_requests_params('get', 'ohlcv', True, market_s, **params)

	@low_deco
	async def sub_ohlcv_up(self, market_s, **params):
		return self.get_requests_params('sub', 'ohlcv_up', True, market_s, **params)

	###{INTERNAL}
	def get_requests_params(self, req_tp, data_tp, market_required, market_s, **params):
		if not market_required:
			if not market_s:
				request_info = {'req_tp': req_tp, 'data_tp': data_tp, **params}
				return request_info
		if isinstance(market_s, str):
			request_info = {'req_tp': req_tp, 'data_tp': data_tp, 'market': market_s, **params}
			return request_info

		if isinstance(market_s, list):
			requests_params = []
			for market in market_s:
				request_info = {'req_tp': req_tp, 'data_tp': data_tp, 'market': market, **params}
				requests_params.append(request_info)
			return requests_params


###
##
#


class Connection_ws(Connection):
	pingpong = False
	connect_params = {}

	@connect_deco
	async def connect(self, **connect_params):
		if connect_params:
			for key, value in connect_params.items():
				self.connect_params[key] = value
		await self.open(**self.connect_params)
		if self.active:
			# self.rec_task=asyncio.create_task(self.rec_forever())

			await self.after_open()

	@disconnect_deco
	async def disconnect(self, **params):
		await self.close()

	"""
	@disconnect_deco
	async def disconnect(self, **params):
		await self.conn_close()
		while self.active:
			await asyncio.sleep(0.1
	"""

	async def open(self, **connect_params):

		if self.connected or self.closed:
			raise Exception('method "connect" has already been used')
			
		self.connected=True
		
		try:
			self.conn = await websockets.connect(self.get_adress(), **connect_params)
		except Exception as E:

			await self.conn_error_case('open', E)

		else:
			self.active = True
			open_report = {
				'tp': 'report',
				'report_tp': 'open',
				'tm': time_ms()
			}
			open_report_parsed = self.parse(open_report)

			await self.callback(open_report_parsed)
		await self.after_open()

	async def send(self, request):
		#print('send', request)
		try:
			await self.conn.send(request)
		except Exception as E:
			if not self.closed:
				await self.conn_error_case('req', E, request=request)
		else:
			send_report = {
				'tp': 'report',
				'report_tp': 'send',
				'request': request,
				'tm': time_ms()
			}
			send_report_parsed = self.parse(send_report)
			if send_report_parsed.get('service'):
				return

			await self.callback(send_report_parsed)

	async def rec_forever(self):
		while not self.closed:
			await self.rec()

	async def rec(self):
		self.received_at_last = time_ms()
		try:

			msg = await self.conn.recv()
		except Exception as E:

			if not self.closed:
				await self.conn_error_case('req', E)
			
		else:
			self.received_at_last = time_ms()
			msg_decoded = self.decode(msg)
			if msg_decoded['tp'] == 'ping':
				if self.pingpong:
					await self.get_pong(ping_msg=msg_decoded['payload'])
			msg_parsed = self.parse(msg_decoded)
			if msg_parsed['tp'] not in self.do_not_return:
				await self.callback(msg_parsed)

	async def close(self):  # нужно не так
		#print('clousing....')
		self.active = False
		self.closed = True
		
		if self.pong_sim_task:
			self.pong_sim_task.cancel()
		if self.service_send_task:
			self.service_send_task.cancel()		

		await self.conn_close()



		close_report = {
			'tp': 'report',
			'report_tp': 'close',
			'tm': time_ms()
		}

		close_report_parsed = self.parse(close_report)
		await self.callback(close_report_parsed)

	async def conn_close(self):
		if self.conn is not None:
			await self.conn.close()

	async def conn_error_case(self, action, exception, **info):
		self.active = False
		self.closed = True
		await self.conn_close()
		conn_error = {
			'tp': 'conn_error',
			'raised_on': action,
			'E':exception,
			**info,
			'tm': time_ms()
		}
		conn_error_parsed = self.parse(conn_error)
		await self.callback(conn_error_parsed)

	def get_adress(self):
		pass


class Websocket_binance(Connection_ws):
	reqs_reserved = {'count': 1, 'per_time': '1s',
					 'per_ms': 1000}  # //допустимые служебные запросы(тоестовый запрос при открыти, сюда же unsub)

	greeting_sim = True  # //при отырытии отправляет запрос на получение текущих подписк,
	# // ответ на этот запрос класифицируется как greeting

	parting_sim = True  # //класифицировать сообщения, после который известно,
	# //что следует сброс соендинения как parting(1 сообщение таким обьразом класифицируетя как 2 разныех, и в калбек возвращается 2 сообщения.)

	pong_sim = True  # //посылать переиодически запрос( при условии не получения данных) который будет класифыицироваться ка pong,
	# //получение pong означает что соендинение живо.
	pong_sim_frequency = '1m'  # //частота с которой посылается понг
	pong_sim_when = 'silent'  # //когда pong симулируется:
	# //	'silent' - только если за время pong_sim_frequency не было получено никаких сообщений
	# //	'always' - отправляется каждые pong_sim_frequency вне зависимости приходят другие данные или нет.

	data_tp_map = {
		'trade': 'trades_up',
		'kline': 'ohlcv_up',
		'depthUpdate': 'orderbook_up',
		'24hrTicker': 'tickers_CHL',
		'24hrMiniTicker': 'tickers_C',
	}

	req_tp_map = {
		'sub': "SUBSCRIBE",
		'unsub': "UNSUBSCRIBE",
		'pong_sim': "LIST_SUBSCRIPTIONS",
		'greeting_sim': "LIST_SUBSCRIPTIONS"

	}

	incoming_msgs = [
		'data',
		'failure',
		'success',
		'conflict',
		'unsub',

		'greeting',
		'pong',
		'parting',

		'conn_error',

		'report',

		'decode_error',
	]

	data_tps = [
		'ohlcv_up',
		'orderbook_up',
		'trades_up',
		'tickers_C',
		'tickers_CHL'
	]

	failure_tps = [
		'too_frequent_requests',
		'invalid_market',
		'too_many_subscriptions'
		'unknown'
	]

	parting_tps = []

	conn_error_tps = [
		'unknown'

	]

	failure_unknown_as_parsing_error = False
	conn_error_unknown_as_parsing_error = False

	templates = {
		'orderbook_up': {
			'sub': {
				'request': "%s@depth%s",
				'order': ['market', 'frequency'],
				'default': {'frequency': 100},
				'requared': ['market'],
				'apply': {
					'frequency': lambda value: '@%sms' % value if value == 100 else ''
				},
				'diff_ignore': ['frequency']
				# diff_ignore - указывает на то что при различии в этом параметре присылаемое сообщение не отличиется ничем
				# так как точное определение запроса невозможно, то мною принято решение ограничивать такие подписки на 1 сокете
				# для biancne так и вовсе подписка перезапустится

			}
		},
		'trades_up': {
			'sub': {
				'request': "%s@trade",
				'order': ['market'],
				'default': {},
				'requared': ['market'],
				'apply': {}

			}
		},
		'tickers_CHL': {
			'sub': {
				'request': '%s',
				'order': ['market'],
				'default': {'market': 'all'},
				'requared': [],
				'apply': {
					'market': lambda value: '!ticker@arr' if value == 'all' else '%s@ticker' % value}
			}
		},
		'tickers_C': {
			'sub': {
				'request': '%s',
				'order': ['market'],
				'default': {'market': 'all'},
				'requared': [],
				'apply': {
					'market': lambda value: '!miniTicker@arr' if value == 'all' else '%s@miniTicker' % value}
			}
		},

		'ohlcv_up': {
			'sub': {
				'request': '%s@kline_%s',
				'order': ['market', 'interval'],
				'default': {'interval': '1m'},
				'requared': ['market'],
				'apply': {
				}
			}

		}

	}

	def __init_children__(self, ):
		self.commands_info = {}  # // {'command_id':{'command_tp': }}
		# //command_tps: 'sub'/'get','greeting_sim'/'pong_sim'/'unsub'
		# // clear after success/failure
		self.for_to_identify = {}  # // {request_normal_tuple_1:track_id_1, ..., request_normal_tuple_n:track_id_n}
		# // req_tp:'sub':clear after unsub or failure, req_tp='get' clear after data or failure
		self.requests_map = {}  # // {request_json_1:req_multi_id_1, ..., request_json_n:req_multi_id_n}
		# // clear after send/send_error
		self.reqs_info = {}  # // {track_id_1:request_params_1, ..., track_id_n:request_params_n}

		self.pong_sim_sleep_max = td_to_sd(self.pong_sim_frequency)

		self.unsub_track_ids = []

		self.service_send_task = None
		self.pong_sim_task=None

		self.service_send_info = {'tm': time_ms() - 1000, 'count': 0}

		self.__init_parser__()

	def __init_parser__(self):
		self.on_incoming_msgs_methods = {msg_tp: getattr(self, 'parse_%s' % msg_tp) for msg_tp in self.incoming_msgs}
		self.on_data_methods = {data_tp: getattr(self, 'parse_data_%s' % data_tp) for data_tp in self.data_tps}

	# {UNSUB_INTERFACE}
	def is_served(self, track_id):
		if self.reqs_info.get(track_id):
			return True
		return False
	
	
	def unsub(self, track_id_s, as_service_req=True):
		"""
		as_service_req:bool 	//True будут использваотсья зарезервированные  запросы для служебных целей, False, запрос выполнится сразу, следует контролировать лимиты выше.
		"""
		# for_to_identify_invert = {v: k for k, v in self.for_to_identify.items()}


		if not isinstance(track_id_s, list):
			track_id_s = [track_id_s]

		for track_id in track_id_s:
			request_params = self.reqs_info.get(track_id)
			if not request_params:
				raise Exception('the connection does not work with the request with track_id=%s' % track_id)

		if as_service_req:

			self.unsub_track_ids.extend(track_id_s)
			self.service_send('unsub')
		else:
			raise NotImplementedError('script not released where as_service_req=False')

	#

	def get_adress(self):
		return "wss://stream.binance.com:9443/ws/" + str(random.randint(1, 999999))

	# {INTERNAL}
	##{SERVICE}
	async def after_open(self):
		self.received_at_last = time_ms()
		asyncio.create_task(self.rec_forever())
		await self.greeting_sim()
		self.pong_sim_task=asyncio.create_task(self.pong_sim_coro())

	async def greeting_sim(self):
		self.service_send('greeting_sim')

	async def pong_sim_coro(self):
		while not self.closed:
			pong_sim_sleep = self.received_at_last + self.pong_sim_sleep_max - time_ms()
			await asyncio.sleep(pong_sim_sleep)
			if self.pong_sim_when == 'always':
				self.service_send('pong_sim')

			elif self.pong_sim_when == 'silent':
				silent_ms = time_ms() - self.received_at_last
				silent_s = int(silent_ms / 1000)
				if self.pong_sim_sleep <= silent_s:
					self.service_send('pong_sim')

	async def pong_sim_coro(self):
		while not self.closed:
			if self.pong_sim_when == 'always':
				await asyncio.sleep(self.pong_sim_sleep_max)
				self.service_send('pong_sim')
			elif self.pong_sim_when == 'silent':
				received_at_last_s = self.received_at_last // 1000
				pong_sim_sleep = received_at_last_s + self.pong_sim_sleep_max - time_s()
				if pong_sim_sleep > 0:
					await asyncio.sleep(pong_sim_sleep)
					continue
				else:
					self.service_send('pong_sim')
					await asyncio.sleep(self.pong_sim_sleep_max)

			else:
				raise Exception('!')

	"""'			
	async def ping(self):


		return future

	"""

	def service_send(self, *args, **kwargs):
		if self.service_send_task:
			self.service_send_queue.put_nowait(*args, **kwargs)
			if self.service_send_task.done():
				# self.service_send_queue.put_nowait(*args, **kwargs)
				self.service_send_task = asyncio.create_task(self.service_send_coro())
		else:
			self.service_send_queue = asyncio.Queue()
			self.service_send_queue.put_nowait(*args, **kwargs)
			self.service_send_task = asyncio.create_task(self.service_send_coro())
			
		if not self.service_send_task:
			self.service_send_queue.put_nowait(*args, **kwargs)
			self.service_send_task = asyncio.create_task(self.service_send_coro())
			
		if self.service_send_task.done():
			self.service_send_task = asyncio.create_task(self.service_send_coro())
		self.service_send_queue.put_nowait(*args, **kwargs)
		
	

	async def service_send_coro(self):
		while not self.service_send_queue.empty():
			send_task = await self.service_send_queue.get()
			now_ms = time_ms()
			last_send_tm_base = self.service_send_info['tm']
			delta_ms = now_ms - last_send_tm_base

			if delta_ms >= self.reqs_reserved['per_ms']:
				sended = await getattr(self, '%s_send_service' % send_task)()

				if sended:
					self.service_send_info['tm'] = time_ms()
					self.service_send_info['count'] = 1

			else:
				if self.service_send_info['count'] < self.reqs_reserved['count']:
					sended = await getattr(self, '%s_send_service' % send_task)()
					if sended:
						last_send_tm_base_control = time_ms()
						if last_send_tm_base_control - last_send_tm_base > self.reqs_reserved['per_ms']:
							self.service_send_info['tm'] = last_send_tm_base_control
							self.service_send_info['count'] = 1
						else:
							self.service_send_info['count'] += 1

				else:
					await asyncio.sleep(delta_ms / 1000)
					sended = await getattr(self, '%s_send_service' % send_task)()
					if sended:
						self.service_send_info['tm'] = time_ms()
						self.service_send_info['count'] = 1

	async def unsub_send_service(self):

		if self.unsub_track_ids:
			unsub_track_ids = self.unsub_track_ids
			self.unsub_track_ids = []
			command_id = self.get_command_id()
			self.commands_info[command_id] = {'tp': 'unsub', 'payload': unsub_track_ids}

			# unsub_track_ids = []
			unsub_requests = []
			for track_id in unsub_track_ids:
				request_params = self.reqs_info.get(track_id)

				request = self.bake_request(request_params)

				unsub_requests.append(request)
			command = self.bake_command('unsub', command_id, unsub_requests)
			self.requests_map[command] = command_id
			self.unsub_command = command

			await self.send(command)
			return True
		else:
			return False

	async def pong_sim_send_service(self):

		command_id = self.get_command_id()
		self.commands_info[command_id] = {'tp': 'pong_sim', 'service': True}
		command = self.bake_command('pong_sim', command_id, None)
		self.requests_map[command] = command_id
		await self.send(command)
		return True

	async def greeting_sim_send_service(self):

		command_id = self.get_command_id()

		self.commands_info[command_id] = {'tp': 'greeting_sim', 'service': True}
		command = self.bake_command('greeting_sim', command_id, None)

		self.requests_map[command] = command_id
		await self.send(command)
		return True

	##

	##{REQUESTS_HANDLING}
	def get_requests_commands(self, requests_params):

		requests_by_req_tp = {}
		for request_params in requests_params:
			req_tp = request_params['req_tp']
			if not requests_by_req_tp.get(req_tp):
				requests_by_req_tp[req_tp] = []
			requests_by_req_tp[req_tp].append(request_params)

		requests_commands = []
		for req_tp, requests_params in requests_by_req_tp.items():
			req_multi_id = self.register_as_1_request(requests_params)
			if not req_multi_id:
				continue

			requests = []
			for request_params in requests_params:
				if request_params.get('conflict'):
					continue

				request = self.bake_request(request_params)
				requests.append(request)

			command = self.bake_command(req_tp, req_multi_id, requests)
			self.requests_map[command] = req_multi_id

			requests_commands.append(command)

		return requests_commands

	def register_as_1_request(self, requests_params):
		command_id = self.get_command_id()
		self.commands_info[command_id] = {'tp': 'sub', 'payload': []}
		conflicts={}
		for request_params in requests_params:

			self.register_request(request_params)
			if request_params.get('conflict'):
				conflicts[request_params['track_id']]=request_params['conflict']
				continue
				
			self.commands_info[command_id]['payload'].append(request_params['track_id'])
		
		if conflicts:
			msg={
				'tp':'conflict',
				'track_ids':list(conflicts.keys()),
				'conflicts':conflicts,
				'tm':time_ms()
			}
			conflict_parsed = self.parse(msg)
			self.schedule_later(self.callback, conflict_parsed)
			
		if not self.commands_info[command_id]['payload']:
			del self.commands_info[command_id]
		else:
			return command_id

	def get_command_id(self):
		if not hasattr(self, 'command_id_last'):
			self.command_id_last = 0
		self.command_id_last += 1

		return self.command_id_last

	def register_request(self, request_params):
		request_normal_tuple = self.to_normal_tuple(request_params)

		track_id_conflict = self.for_to_identify.get(request_normal_tuple)
		if track_id_conflict:
			
			request_params['conflict'] = track_id_conflict

		else:
			self.for_to_identify[request_normal_tuple] = request_params['track_id']
			self.reqs_info[request_params['track_id']] = request_params.copy()
	
	def schedule_later(self, method, *args, **kwargs):
		'''
		запланировать вызов метода после текущего события в цикле
		'''
		asyncio.create_task(self.execute_later(method, *args, **kwargs))
	async def execute_later(self, method, *args, **kwargs):
		method(*args, **kwargs)
		



	def to_normal_tuple(self, request_params):
		params_list = []
		req_tp = request_params['req_tp']
		data_tp = request_params['data_tp']
		params_list.append(req_tp)
		params_list.append(data_tp)
		for param in self.templates[data_tp][req_tp]['order']:
			if param not in self.templates[data_tp][req_tp].get('diff_ignore', []):
				value = request_params.get(param)
				if not value:
					value = self.templates[data_tp][req_tp]['default'][param]
				params_list.append(value)
		return tuple(params_list)

	def bake_request(self, request_params):

		if request_params.get('market'):
			request_params['market'] = self.symbol_to_external_format(request_params['market'])
		req_tp = request_params['req_tp']
		data_tp = request_params['data_tp']
		params_info = self.templates[data_tp][req_tp]
		params_adapted = []
		for param in params_info['order']:
			value = request_params.get(param, None)
			if value is None:
				if param not in params_info['requared']:
					value = params_info['default'][param]
				else:
					raise Exception('required parameter %s not passed' % param)

			value = params_info['apply'].get(param, lambda value: value)(value)
			params_adapted.append(value)
		request = params_info['request'] % tuple(params_adapted)

		return request

	def bake_command(self, req_tp, command_id, requests=None):

		command = {}
		command['method'] = self.req_tp_map[req_tp]
		command['id'] = command_id
		if requests:
			command['params'] = requests

		return json.dumps(command)

	def symbol_to_external_format(self, symbol_internal):
		base, quote = symbol_internal.split('-')
		symbol_external = ''.join([quote, base])
		self.update_symbols_map({symbol_external: symbol_internal})
		return symbol_external.lower()

	##
	##{DECODING}
	def decode(self, msg):
		tm = time_ms()
		try:
			msg = json.loads(msg)
			return {
				'tp': 'unknown',
				'payload': msg,
				'tm': tm
			}
		except Exception as E:
			return {
				'tp': 'decode_error',
				'payload': msg,
				'exception': E,
				'tm': tm
			}

	##{PARSING}
	def parse(self, msg):

		parsed_msg = {}
		try:
			msg_tp = self.indentify_msg_tp(msg)

			parsed_msg = {
				'tp': msg_tp,
				**self.on_incoming_msgs_methods[msg_tp](msg),
				'tm': msg['tm']
			}
			return parsed_msg
		except Exception as E:
			return self.return_parsing_error(msg, E)

	def indentify_msg_tp(self, msg):
		"""
		failure example
		{"error":{"code":2,"msg":"Invalid request: missing field `method` at line 4 column 1"},"id":3}
		{"error":{"code":4,"msg":"Too many subscriptions"},"id":1}
		не могу найти на binance описания кодов ошибок websocket
		"""
		msg_tp = msg['tp']
		if msg_tp == 'unknown':
			payload = msg['payload']

			if isinstance(payload, dict):
				if payload.get('e'):
					return 'data'

				elif dict_funcs.consists_of_keys(payload, 'result', 'id'):
					command_id = payload['id']
					command_tp = self.commands_info[command_id]['tp']
					if command_tp == 'sub':
						return 'success'
					elif command_tp == 'greeting_sim':
						return 'greeting'
					elif command_tp == 'pong_sim':
						return 'pong'
					elif command_tp == 'unsub':
						return 'unsub'

				elif dict_funcs.consists_of_keys(payload, 'error', 'msg', 'id'):
					return 'failure'
				raise Unknown_msg_tp()


			elif isinstance(payload, list):
				if len(list) > 0:
					isnt_data = sum([not part.get('e') for part in payload])
					if not isnt_data:
						return 'data'
		elif msg_tp in self.incoming_msgs:
			return msg_tp
		raise Unknown_msg_tp()

	def parse_success(self, msg):
		payload = msg['payload']
		command_id = payload['id']
		command_info = self.commands_info.pop(command_id)

		track_ids = command_info['payload']
		success_parsed = {
			'track_ids': track_ids
		}
		return success_parsed

	def parse_unsub(self, msg):
		command_id = msg['payload']['id']
		command_info = self.commands_info.pop(command_id)
		track_ids = command_info['payload']
		for_to_identify_invert = {v: k for k, v in self.for_to_identify.items()}
		for track_id in track_ids:
			del self.for_to_identify[for_to_identify_invert[track_id]]
			del self.reqs_info[track_id]
		return {
			'track_ids': track_ids
		}

	def parse_pong(self, msg):
		command_id = msg['payload']['id']
		self.commands_info.pop(command_id)
		return {}

	def parse_greeting(self, msg):
		"""
		приветсвенное сообщение для binance отсутвует,
		но можно отправлять запрос(не подписку, на который придет только 1 ответ
		например для binance можно запросить список подписок.)
		полученое сообщение воспринимать как приветсвие.
		"""

		command_id = msg['payload']['id']
		self.commands_info.pop(command_id)
		return {}

	def parse_parting(self, msg):
		"""
		прощальные сообщения отсутвуют.
		однако после failure следует разрыв,
		значит нужно решить, можно ли 1 сообщение класифицировать
		по 2 типам, и, возможно генерировать 2 сообщения
		1. failure_tp - сообщает о том что подписки не осуществленны
		2. parting - говрит о сбросе соендинения, причина - был запрос какой-то не такой.
		"""
		pass

	def parse_failure(self, msg):
		"""
		{"error":{"code":2,"msg":"Invalid request: missing field `method` at line 4 column 1"},"id":3}
		{"error":{"code":4,"msg":"Too many subscriptions"},"id":1}
		"""
		failure_tp = self.identify_failure_tp(msg)
		if failure_tp == 'unknown' and self.failure_unknown_as_parsing_error:
			raise Unknown_failure_tp()

		payload = msg['payload']
		command_id = payload['id']
		command_info = self.commands_info.pop(command_id)
		track_ids = command_info['payload']
		failure_parsed = {
			'failure_tp': failure_tp,
			failure_tp: msg['payload'],
			'track_ids': track_ids
		}
		return failure_parsed

	def identify_failure_tp(self, msg):
		error = msg['payload']['error']
		code = error['code']
		msg = error['msg']

		if code == 1:
			return 'unknown'  # //invalid value type

		if code == 2:
			return 'unknown'  # //invalid_request:
		if code == 3:
			return 'unknown'  # //invalid_json

		if code == 4:
			if msg == 'Too many subscriptions':
				return 'too_many_subscriptions'
			else:
				return 'unknown'
		return 'unknown'

	def parse_report(self, msg):
		if msg['report_tp'] == 'send':
			command_id = self.requests_map.pop(msg['request'])
			if self.commands_info[command_id].get('service'):
				return {
					'service': True
				}
			else:
				return {
					'report_tp': 'send',
					'send_tp': self.commands_info[command_id]['tp'],
					'track_ids': self.commands_info[command_id]['payload']

				}

		return {
			'report_tp': msg['report_tp']
		}

	def parse_conflict(self, msg):
		"""
		reasons:
			1.This subscription will overwrite an existing same subscription
			(or which is perceived by the exchange as the same).
			2.a message for a requested subscription is indistinguishable from a message
			for another subscription. prohibited to the impossibility of tracking
		solutions:
			1.Start this subscription on a different connection,
			2.call "connection.unsub (track_id_conflict)" and request a subscription again.
		"""
		return {
			'track_ids':msg['track_ids'],
			'conflicts':msg['conflicts']
		}

	def parse_conn_error(self, msg):
		"""
		"""
		conn_error_tp = self.identify_conn_error_tp(msg)
		return {
			'conn_error_tp': conn_error_tp,
			'raised_on': msg['raised_on'],
			'exception': msg['E'],
			#'last_send': self.last_send_parsed,
			#'last_rec': self.last_rec_parsed
		}

	def identify_conn_error_tp(self, msg):
		return 'unknown'

	def parse_decode_error(self, msg):
		return {
			'exception': msg['exception'],
			'raw': msg['raw']
		}

	def return_parsing_error(self, msg, E):
		return {
			'tp': 'parsing_error',
			'exception': E,
			'raw': msg,
			'tm': msg['tm']
		}

	def parse_data(self, msg):
		data_tp = self.identify_data_tp(msg)
		parsed_data = {
			'data_tp': data_tp,
			**self.on_data_methods[data_tp](msg)
		}
		return parsed_data

	def identify_data_tp(self, msg):
		if isinstance(msg, list):
			data_tp_exchange = msg['payload'][0]['e']
		else:
			data_tp_exchange = msg['payload']['e']

		data_tp = self.data_tp_map.get(data_tp_exchange)
		if data_tp:
			return data_tp
		else:
			raise Unknown_data_tp()

	def parse_data_ohlcv_up(self, msg):
		"""
		{
		"e": "kline",	 // Event type
		"E": 123456789,   // Event time
		"s": "BNBBTC",	// Symbol
		"k": {
		"t": 123400000, // Kline start time
		"T": 123460000, // Kline close time
		"s": "BNBBTC",  // Symbol
		"i": "1m",	  // Interval
		"f": 100,	   // First trade ID
		"L": 200,	   // Last trade ID
		"o": "0.0010",  // Open price
		"c": "0.0020",  // Close price
		"h": "0.0025",  // High price
		"l": "0.0015",  // Low price
		"v": "1000",	// Base asset volume
		"n": 100,	   // Number of trades
		"x": false,	 // Is this kline closed?
		"q": "1.0000",  // Quote asset volume
		"V": "500",	 // Taker buy base asset volume
		"Q": "0.500",   // Taker buy quote asset volume
		"B": "123456"   // Ignore
		}
		}
		"""
		payload = msg['payload']
		kline_raw = payload['k']
		market = self.symbol_to_internal_format(kline_raw['s'])

		kline = {
			'open_tm': kline_raw['t'],
			'close_tm': kline_raw['T'],
			'o': float(kline_raw['o']),
			'h': float(kline_raw['h']),
			'l': float(kline_raw['l']),
			'c': float(kline_raw['c']),
			'qv': float(kline_raw['q']),
			'bv': float(kline_raw['v']),
			'custom': {
				'closed': kline_raw['x'],
				'trades_count': kline_raw['n'],
				'bv_tacker_buy':float(kline_raw['V']),
				'qv_tacker_buy': float(kline_raw['Q']),
			}
		}

		interval = kline_raw['i']

		request_normal_tuple = ('sub', 'ohlcv_up', market, interval)

		request_params_or_track_id = self.for_to_identify[request_normal_tuple]
		if isinstance(request_params_or_track_id, dict):
			return {
				'ohlcv_up': kline,
				'request_params': request_params_or_track_id
			}
		else:
			return {
				'ohlcv_up': kline,
				'track_id': request_params_or_track_id
			}

	def parse_data_orderbook_up(self, msg):
		"""
		{
		'e': 'depthUpdate',
		'E': 1622207997012,
		's': 'ETHBTC',
		'U': 3287357200,
		'u': 3287357200,
		'b': ['0.07024000', '1.00000000'],
		'a': [['0.07024000', '0.00000000']]
		}
		 """

		raw = msg['payload']
		market = self.symbol_to_internal_format(raw['s'])
		tm = np.datetime64(raw['E'], 'ms')
		received_at = np.datetime64(msg['tm'], 'ms')
		id_start = raw['U']
		id = raw['u']
		bids = [[float(step[0]), float(step[1])] for step in raw['b']]
		asks = [[float(step[0]), float(step[1])] for step in raw['a']]

		orderbook_up = {
			'tm': tm,
			'received_at': received_at,
			'id_start': id_start,
			'id': id,
			'bids': bids,
			'asks': asks
		}

		request_normal_tuple = ('sub', 'orderbook_up', market)
		track_id = self.for_to_identify[request_normal_tuple]
		return {
			'orderbook_up': orderbook_up,
			'track_id': track_id
		}

	def parse_data_trades_up(self, msg):
		"""
		{
		"e": "trade",	 // Event type
		"E": 123456789,   // Event time
		"s": "BNBBTC",	// Symbol
		"t": 12345,	   // Trade ID
		"p": "0.001",	 // Price
		"q": "100",	   // Quantity
		"b": 88,		  // Buyer order ID
		"a": 50,		  // Seller order ID
		"T": 123456785,   // Trade time
		"m": true,		// Is the buyer the market maker?
		"M": true		 // Ignore
		}
		"""

		trade_raw = msg['payload']
		market = self.symbol_to_internal_format(trade_raw['s'])

		trade = {
			'id': trade_raw['t'],
			'tm': trade_raw['T'],
			'price': float(trade_raw['p']),
			'amount': float(trade_raw['q']),
			'buyer_maker': trade_raw['m'],
			'custom': {
				'bid_id': trade_raw['b'],
				'ask_id': trade_raw['a'],
				'event_tm': trade_raw['E'],
				'best_match': trade_raw['M']
			}
		}

		request_normal_tuple = ('sub', 'trades_up', market)
		track_id = self.for_to_identify[request_normal_tuple]
		return {
			'trades_up': [trade],
			'track_id': track_id
		}

	def parse_data_tickers_C(self, msg):
		"""
		{
		"e": "24hrMiniTicker",  // Event type
		"E": 123456789,		 // Event time
		"s": "BNBBTC",		  // Symbol
		"c": "0.0025",		  // Close price
		"o": "0.0010",		  // Open price
		"h": "0.0025",		  // High price
		"l": "0.0010",		  // Low price
		"v": "10000",		   // Total traded base asset volume
		"q": "18"			   // Total traded quote asset volume
		}
		"""
		tickers_raw = msg['payload']
		tickers = []
		if isinstance(tickers_raw, list):
			market = None
			for ticker_raw in tickers_raw:
				ticker = {
					'market': self.symbol_to_internal_format(ticker_raw['symbol']),
					'C': float(ticker_raw['c'])
				}
				tickers.append(ticker)
		else:
			ticker_raw = tickers_raw
			market = self.symbol_to_internal_format(ticker_raw['symbol'])
			ticker = {
				'market': market,
				'C': float(ticker_raw['c'])
			}
			tickers.append(ticker)

		request_normal_tuple = ('sub', 'tickers_C', market)
		track_id = self.for_to_identify[request_normal_tuple]

		return {
			'tickers_C': tickers,
			'track_id': track_id
		}

	def parse_data_tickers_CHL(self, msg):
		"""
		{
		"e": "24hrTicker",  // Event type
		"E": 123456789,	 // Event time
		"s": "BNBBTC",	  // Symbol
		"p": "0.0015",	  // Price change
		"P": "250.00",	  // Price change percent
		"w": "0.0018",	  // Weighted average price
		"x": "0.0009",	  // First trade(F)-1 price (first trade before the 24hr rolling window)
		"c": "0.0025",	  // Last price
		"Q": "10",		  // Last quantity
		"b": "0.0024",	  // Best bid price
		"B": "10",		  // Best bid quantity
		"a": "0.0026",	  // Best ask price
		"A": "100",		 // Best ask quantity
		"o": "0.0010",	  // Open price
		"h": "0.0025",	  // High price
		"l": "0.0010",	  // Low price
		"v": "10000",	   // Total traded base asset volume
		"q": "18",		  // Total traded quote asset volume
		"O": 0,			 // Statistics open time
		"C": 86400000,	  // Statistics close time
		"F": 0,			 // First trade ID
		"L": 18150,		 // Last trade Id
		"n": 18151		  // Total number of trades
		}
		"""
		tickers_raw = msg['payload']
		tickers = []
		if isinstance(tickers_raw, list):
			market = None
			for ticker_raw in tickers_raw:
				ticker = {
					'market': self.symbol_to_internal_format(ticker_raw['symbol']),
					'C': float(ticker_raw['c']),
					'H': float(ticker_raw['b']),
					'L': float(ticker_raw['a'])
				}
				tickers.append(ticker)
		else:
			ticker_raw = tickers_raw
			market = self.symbol_to_internal_format(ticker_raw['symbol'])
			ticker = {
				'market': market,
				'C': float(ticker_raw['c']),
				'H': float(ticker_raw['b']),
				'L': float(ticker_raw['a'])
			}
			tickers.append(ticker)

		request_normal_tuple = ('sub', 'tickers_CHL', market)
		track_id = self.for_to_identify[request_normal_tuple]

		return {
			'tickers_CHL': tickers,
			'track_id': track_id
		}
	###{PARSING.INTERNAL}
	def symbol_to_internal_format(self, symbol_external):
		symbol_internal = self.symbols_map.get(symbol_external)
		if not symbol_internal:
			raise Unknown_market(symbol_external)
		return symbol_internal

	def update_symbols_map(self, symbols_map):
		for internal_view, external_view in symbols_map.items():
			self.symbols_map[internal_view.upper()] = external_view.upper()
	###
	##
	#
#[END:Websocket_binance]


