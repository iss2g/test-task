#from mda.core.base.receivers.rest.connection import *
import numpy as np
from itertools import count as sequence

from time_funcs import dtHttp_to_dt64


#print('reloading_conn')


'''
HTTP 4XX return codes are used for malformed requests; the issue is on the sender's side.
HTTP 403 return code is used when the WAF Limit (Web Application Firewall) has been violated.
HTTP 429 return code is used when breaking a request rate limit.
HTTP 418 return code is used when an IP has been auto-banned for continuing to send requests after receiving 429 codes.
HTTP 5XX return codes are used for internal errors; the issue is on Binance's side.
With using /wapi/v3 , HTTP 504 return code is used when the API successfully sent the message but not get a response within the timeout period. It is important to NOT treat this as a failure operation; the execution status is UNKNOWN and could have been a success.


{
  "code":-1121,
  "msg":"Invalid symbol."
}


'''
import pickle as pl
import inspect
import os.path

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientConnectorError
#import ClientConnectorError
import time
import asyncio

import asyncio
import time
from copy import deepcopy
from inspect import iscoroutinefunction

# from mda.core.base.receivers.response_tps import *	# OPEN, CLOSE, DATA, ERROR, SUCCESS, DECODE_ERROR


'''
async def callback_example(result, id):
	pass
'''


def connect_deco(method):
	async def connect_wrapper(self, *args, **kwargs):
		if self.connected or self.closed:
			raise Exception('method "connect" has already been used')

		await method(self, *args, **kwargs)

		self.connected = True

	# await self.callback({'tp': 'open', 'data': None, 'tm': time.time()})

	return connect_wrapper


def disconnect_deco(method):
	async def disconnect_wrapper(self, *args, **kwargs):
		if self.closed:
			raise Exception('connection already closed')
		self.closed = True
		await method(self, *args, **kwargs)

	# await self.callback({'tp': 'close', 'data': None, 'tm': time.time()})

	return disconnect_wrapper


def low_deco(method):
	def wrapper(self, *args, **kwargs):
		requests_params = method(self, *args, **kwargs)
		return self.req_low(requests_params)

	return wrapper


class Connection_base():
	connect_params = {}

	def __init__(self, callback, do_not_return=None, auto_connect=False, connect_params=None):
		'''
		callback:coroutine
		auto_connect:bool	//True - calling the "connect" method is not required, at the start of requests, "connect" will be called automatically,
					//False - call "connect" is required
		auto_disconect		//??

		'''
		self.id_sequence=sequence(1)
		self.closed = False
		self.active = False
		self.connected = False
		self.conn = None
		self.conn_coro = None

		self.callback = callback
		self.do_now_return = (
			do_not_return if isinstance(do_not_return, list) else [do_not_return]) if do_not_return else []
		self.auto_connect = auto_connect
		# self.auto_disconect = auto_disconnect

		self.connect_params = deepcopy(self.connect_params)
		if connect_params:
			for key, value in connect_params.items():
				self.connect_params[key] = value

	# {CONNECTION_CONTROL_INTERFACE}

	@connect_deco
	async def connect(self, **connect_params):
		raise NotImplementedError

	@disconnect_deco
	async def disconnect(self):
		raise NotImplementedError

	def is_ready(self):
		'''
		1.готово ли соендиение к подпискам
		'''
		return self.is_connected() and not self.closed

	def is_active(self):
		'''
		1.готово ли соендиение к подпискам(частный случай is_ready), но в отличии от is_ready еще показывает, что соендинение фактически функционирует
		'''
		if self.active:
			return True

	def is_connected(self):
		'''
		1.показывает надобность в connect
		'''
		return self.connected or self.auto_connect

	def is_closed(self):
		'''
		1. показывает что соендинение не было сброшенно
		'''
		return self.closed

	##{INTERNAL}
	def get_url(self, **params):
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

	def generate_requests(self, requests_params):
		raise NotImplementedError

	def send_request(self, request):
		raise NotImplementedError

	# await def run(self):
	#	raise NotImplementedError

	#

	# {REQUESTS_INTERFACE}
	##{LOW}

	def req_low(self, requests_params, callback=None, timeout=None):
		'''
		callback: func(msg, id) or None
		'''
		if self.closed:
			raise Exception('the connection was closed')
		if not self.connected:
			raise Exception('connection not yet open')

		futures = None

		if isinstance(requests_params, list):
			out_is_list = True
		else:
			out_is_list = False
			requests_params = [requests_params]

		track_ids = [next(self.id_sequence) for i in range(len(requests_params))]
		#print(requests_params)
		requests= self.generate_requests(requests_params)
		
		#print(requests)
		if callback or self.callback:
			if callback:
				callbacks = [self.get_tracked_callback(callback, track_id) for track_id in track_ids]
			else:
				callbacks = [self.get_tracked_callback(self.callback, track_id) for track_id in track_ids]
		
		else:
			futures = [asyncio.Future()  for i in range(len(requests_params))]
			callbacks = [future.set_result for future in futures]

		for request, callback, track_id, request_params in zip(requests, callbacks, track_ids, requests_params):
			self.send_request(request, callback, track_id, request_params, timeout)

		if futures:
			if out_is_list:
				return futures
			else:
				 return futures[0]
		if out_is_list:
			return track_ids
		else:
			return track_ids[0]


	def get_tracked_callback(self, callback, track_id):
		def callback_tracked(msg):
			return callback(msg, track_id=track_id)

		return callback_tracked


	##
	##{HIGH}
	@low_deco
	def sub_trades_up(self, market_s, **params):
		return self.get_requests_params('sub', 'trades', True, market_s, **params)


	@low_deco
	def sub_orderbook_up(self, market_s, ** params):
		return self.get_requests_params('sub', 'deltas', True, market_s, **params)


	@low_deco
	def sub_tickers_C(self, market_s=None, **params):
		return self.get_requests_params('sub', 'tickers_C', False, market_s, **params)


	@low_deco
	def sub_tickers_CHL(self, market_s=None, **params):
		return self.get_requests_params('sub', 'tickers_CHL', False, market_s, **params)


	@low_deco
	def get_orderbook(self, market_s, **params):
		return self.get_requests_params('get', 'orderbook', True, market_s, **params)


	@low_deco
	def get_trades(self, market_s, **params):
		return self.get_requests_params('get', 'trades', True, market_s, **params)


	@low_deco
	def get_tickers_C(self, market_s=None, **params):
		return self.get_requests_params('get', 'tickers_C', False, market_s, **params)


	@low_deco
	def get_tickers_CHL(self, market_s=None, **params):
		return self.get_requests_params('get', 'tickers_CHL', False, market_s, **params)


	@low_deco
	def get_pong(self, market_s=None, **params):
		return self.get_requests_params('get', 'pong', False, market_s, **params)


	@low_deco
	def get_trades(self, market_s=None, **params):
		return self.get_requests_params('get', 'trades', True, market_s, **params)


	@low_deco
	def get_orderbook(self, market_s=None, **params):
		return self.get_requests_params('get', 'orderbook', True, market_s, **params)


	@low_deco
	def get_tickers_CHL(self, market_s=None, **params):
		return self.get_requests_params('get', 'tickers_CHL', False, market_s, **params)


	@low_deco
	def get_tickers_C(self, market_s=None, **params):
		return self.get_requests_params('get', 'tickers_C', False, market_s, **params)


	@low_deco
	def get_markets(self, market_s=None, **params):
		return self.get_requests_params('get', 'markets', False, market_s, **params)


	@low_deco
	def sub_ohlcv_up(self, market_s, **params):
		return self.get_requests_params('get', 'ohlcv_up', True, market_s, **params)

	@low_deco
	def get_ohlcv(self, market_s, **params):
		#print(params)
		return self.get_requests_params('get', 'ohlcv', True, market_s, **params)


	###{INTERNAL}
	def get_requests_params(self, req_tp, data_tp, market_required, market_s, **params):
		if not market_required:
			if not market_s:
				request_info = {'req_tp': req_tp, 'data_tp': data_tp, **params}
				return request_info

		if not isinstance(market_s, list):
			market_s = [market_s]
		# market_s = [self.market_to_exfrmt(market) for market in market_s]

		requests_params = []
		for market in market_s:
			request_info = {'req_tp': req_tp, 'data_tp': data_tp, 'market': market, **params}
			requests_params.append(request_info)
		return requests_params


	###
	##
	#


# from mda.core.base.receivers.response_tps import *	# OPEN, CLOSE, DATA, ERROR, SUCCESS, DECODE_ERROR
# from mda.core.base.receivers.rest.error_tps import * # NOT_CONNECTION, UNKNOWN, REQUESTS_TIMEOUT, INVALID_REQUEST, INVALID_MARKET

class  SymbolParsingError(Exception):
	pass

class Connection_rest(Connection_base):
	connect_params = {}
	semaphore_value = 1000
	# session=None
	semaphore = None
	from_request_to_request_params = {}

	incoming_msgs = [
		'data',
		'error',
		'decode_error'

	]

	data_tps = [
		'orderbook',
		'trades',
		'tickers_C',
		'tickers_CHL',
		'markets',
		'ohlcv'
	]

	error_tps = [
		'network_down',
		'too_many_requests',
		'invalid_market',
		'service_unavailable',
		'repeat',
		'unknown_error'
	]

	def __init__(self, *args, **kwargs):
		super().__init__(*args,**kwargs)
	
		self.get_tasks = {}
		self.basequote_map = {}
		#self.quotebase_map = {}

		self.on_incoming_msgs_methods = {msg_tp: getattr(self, 'parse_%s' % msg_tp) for msg_tp in self.incoming_msgs}
		self.on_data_methods = {data_tp: getattr(self, 'parse_data_%s' % data_tp) for data_tp in self.data_tps}


		#
		self.request_coros=set()

	# self.on_error_methods = {error_tp: getattr(self, 'parse_%s' % error_tp) for error_tp in self.error_tps}

	@connect_deco
	async def connect(self, decode=True, parse=True, **connect_params):
		'''

		'''
		self.active = True
		self.semaphore = asyncio.Semaphore(self.semaphore_value)
		self.session = ClientSession(timeout=60, **connect_params)
		'''
		async with  ClientSession() as self.session:
			await asyncio.sleep('always')
		'''
		
	def connect_nowait(self, **connect_params):
		print('connect')
		if self.connected or self.closed:
			raise Exception('method "connect" has already been used')
		self.active = True
		self.semaphore = asyncio.Semaphore(self.semaphore_value)
		self.session = ClientSession(**connect_params)
		self.connected = True
		

	@disconnect_deco
	async def disconnect(self, wait_for_responses=True):

		await self.session.close()

		while self.get_tasks:
			await asyncio.sleep(0.1)
		self.active = False
		
	async def close(self):
		await self.disconnect()

	def send_request(self, request, callback, track_id, request_params, timeout=None):
		callback = self.set_task_removing_extension_to_callback(callback, track_id)
		get_task = asyncio.create_task(self.get(request, callback, timeout, request_params=request_params))
		self.get_tasks[track_id] = get_task
		return get_task

	def set_task_removing_extension_to_callback(self, callback, track_id):
		def callback_extended(msg):
			self.get_tasks.pop(track_id)
			return callback(msg)

		return callback_extended

	async def get(self, request, callback, timeout=None, **about_request):
		default_timeout=30
		async with self.semaphore:
			response = None
			try:
				#print('sending_request')
				#print(request)
				req_coro=asyncio.create_task(self.session.get(request, timeout=timeout or default_timeout))
				self.request_coros.add(req_coro)
				response = await asyncio.wait_for( req_coro, 30 )
				self.request_coros.remove(req_coro)
				#print('response recieved')

			except asyncio.exceptions.TimeoutError as TimeoutError:
				#print('response failed')
				result = {
					'msg_tp': 'error',
					'msg': TimeoutError,
					'status_code': -2,
					'request': request,
					**about_request,
					'tm': time.time()
				}


			except ClientConnectorError as conn_error:
				#print('response failed')
				# self.E=E
				result = {'msg_tp': 'error',
						  'msg': conn_error,
						  'status_code': 0,
						  'request': request,
						  **about_request,
						  'tm': time.time()}
			except Exception as E:
				#print('response failed')
				result = {
					'msg_tp': 'error',
					'msg': E,
					'status_code': -1,
					'request': request,
					**about_request,
					'tm': time.time()
				}
			finally:
				if response:
					try:
						result = {
							'msg_tp': 'unknown',
							'msg': await response.json(),
							'headers': response.headers,
							'status_code': response.status,
							'request': request,
							** about_request,
						   'tm': time.time()
						}
					except Exception as E:
						result = {
							'msg_tp': 'unknown',
							'msg':E,
							'headers': response.headers,
							'status_code': response.status,
							'request': request,
							** about_request,
							'tm': time.time()
						}
					finally:
						response.close()

				decoded = self.decode(result)
				parsed = self.parse(decoded)
				callback(parsed)
			# self.response=response

	def generate_requests(self, requests_params):
		return [self.generate_request(request_params) for request_params in requests_params]

	def generate_request(self, request_params):
		#print(request_params)
		# self.requests_params_map[track_id]=request_params

		req_tp = request_params['req_tp']
		data_tp = request_params['data_tp']
		template_info = self.templates[data_tp][req_tp]
		insert_params = []
		#print(request_params)
		for param in template_info['order']:
			param_value = request_params.get(param)
			if param_value is None:
				param_value = template_info['default'][param]
			elif param == 'market':
				param_value = self.symbol_to_exfrmt(param_value)
			param_value = template_info['apply'].get(param, lambda value: value)(param_value)
			insert_params.append(param_value)
		#print(insert_params)
		request = self.url + template_info['request_postfix'] % tuple(insert_params)
		#print(request)
		return request

	def decode(self, raw):
		return raw

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
		if msg['msg_tp'] == 'unknown':
			if msg[
				'status_code'] == 200:  # для окекса 200 может прийти если запршенна япара не сущеммствует или в запросе отсвуют требуеые параметры
				msg_tp = 'data'
			else:
				msg_tp = 'error'
			return msg_tp
		else:
			return msg['msg_tp']

	def parse_data(self, msg):
		data_tp = self.identify_data_tp(msg)
		parsed_data = {
			'data': self.on_data_methods[data_tp](msg)
		}
		return parsed_data

	def identify_data_tp(self, msg):
		data_tp = msg['request_params']['data_tp']
		return data_tp

	def parse_data_orderbook(self, msg):
		raise NotImplementedError

	def parse_data_trades(self, msg):
		raise NotImplementedError

	def parse_data_tickers_CHL(self, msg):
		raise NotImplementedError

	def parse_data_tickers_C(self, msg):
		raise NotImplementedError

	def parse_data_markets(self, msg):
		raise NotImplementedError

	def parse_data_ohlcv(self, msg):
		raise NotImplementedError

	def parse_error(self, msg):
		error_tp = self.indentify_error_tp(msg)
		parsed_error = {
			'error_tp': error_tp,
			'msg': msg['msg'],
			'about_msg': {
				'headers': msg.get('headers'),
				'status_code': msg['status_code'],
				'request': msg['request']
			}
		}
		return parsed_error

	def indentify_error_tp(self, msg):
		raise NotImplementedError

	def parse_decode_error(self, msg):
		pass

	def return_parsing_error(self, msg, E):
		return {
			
			'tp': 'parsing_error',
			'exception': E,
			'unparsed': msg,
			'tm': msg['tm']
		}

	def symbol_to_exfrmt(self, symbol):
		base, quote = self.extract_basequote_infrmt(symbol)
		symbol = self.join_basequote_exfrmt(base, quote)
		return symbol

	def symbol_to_infrmt(self, symbol):
		#print(symbol)
		base, quote = self.extract_basequote_exfrmt(symbol)
		symbol = self.join_basequote_infrmt(base, quote)
		return symbol

	def extract_basequote_infrmt(self, symbol):
		quote, base = symbol.split('-')
		return base, quote

	def extract_basequote_exfrmt(self, symbol):
		basequote = self.basequote_map.get(symbol)
		#print(basequote)
		if not basequote:
			raise SymbolParsingError()
		base, quote = basequote
		return base, quote

	def join_basequote_infrmt(self, base, quote):
		return f'{quote}-{base}'

	def pass_basequote_map(self, basequote_map):
		self.basequote_map.update(basequote_map)

	def update_basequote_map(self, exfrmt, base, quote):
		self.basequote_map.update({exfrmt:(base.upper(), quote.upper())})
import numpy as np
class Connection(Connection_rest):
	url = 'https://api.binance.com'

	templates = {
		'markets': {
			'get': {
				'request_postfix': '/api/v3/exchangeInfo',
				'order': [],
				'default': {},
				'requared': [],
				'apply': {}
			}
		},
		'orderbook': {
			'get': {
				'request_postfix': '/api/v3/depth?symbol=%s&limit=%s',
				'order': ['market', 'depth'],
				'default': {'depth': 1000},
				'requared': ['market'],
				'apply': {}
			}
		},

		'trades': {
			'get': {
				'request_postfix': '/api/v3/trades?symbol=%s&limit=%s',
				# historicalTrades для того чтобы достатать боле естарые данные на днынй момент не реализованно так как требует X-MBX-APIKEY
				'order': ['market', 'limit'],
				'default': {'limit': 1000},
				'requared': ['market'],
				'apply': {}
			}
		},

		'tickers_CHL': {
			'get': {
				'request_postfix': '/api/v3/ticker/24hr%s',
				'order': ['market'],
				'default': {'market': ''},
				'requared': [],
				'apply': {
					'market': lambda value: '?symbol=%s' % value if value else ''
				}
			}
		},

		'tickers_C': {
			'get': {
				'request_postfix': '/api/v3/ticker/price%s',
				'order': ['market'],
				'default': {'market': ''},
				'requared': [],
				'apply': {
					'market': lambda value: '?symbol=%s' % value if value else ''
				}
			}
		},
		'ohlcv': {
			'get': {
				'request_postfix': '/api/v3/uiKlines?symbol=%s&interval=%s&limit=%s%s%s',
				'order':['market', 'interval', 'limit', 'start', 'end'],
				'default': {'interval': '1m', 'limit': 1000, 'start': None, 'end': None},
				'requared': ['market'],
				'apply': {
						'start': lambda value: '&startTime=%s' % value if value!=None  else '',
						'end':lambda value: '&endTime=%s' % value!=None if value else ''
				 }
			}
		}
	}
	


	market_activity_map={'TRADING':True }

	# {symbols_converting}

	def join_basequote_exfrmt(self, base, quote):
		exfrmt = f'{base}{quote}'
		if not self.basequote_map.get(exfrmt):
			self.basequote_map[exfrmt] = (base, quote)
		return exfrmt



	#

	def parse_data_orderbook(self, msg):
		tm = dtHttp_to_dt64(msg['headers']['Date'])
		received_at = np.datetime64(np.datetime64(int(msg['tm'] * 1000), 'ms'))
		market = msg['request_params']['market']
		orderbook_raw = msg['msg']
		id = msg['msg']["lastUpdateId"]
		orderbook = {
			'id': id,
			'tm': tm,
			'bids': [[float(delta[0]), float(delta[1])] for delta in orderbook_raw['bids']],
			'asks': [[float(delta[0]), float(delta[1])] for delta in orderbook_raw['asks']],
			'received_at': received_at,
		}
		return orderbook

	def parse_data_markets(self, msg):
		markets_info_raw = msg['msg']['symbols']
		basequote_map = {}

		markets_info = {}
		for market_info_raw in markets_info_raw:

			symbol_exfrmt = market_info_raw["symbol"]
			base = market_info_raw["baseAsset"]
			quote = market_info_raw["quoteAsset"]
			self.update_basequote_map(symbol_exfrmt, base, quote)
			market=self.symbol_to_infrmt(symbol_exfrmt)			
			if not 'SPOT' in market_info_raw['permissions']:
				continue
			markets_info[market] = {
				'market':market,
				'symbol':symbol_exfrmt,
				'base': base,
				'quote': quote,
				'created_at': None,
				'is_active': self.market_activity_map.get(market_info_raw['status'], False),
				'status':market_info_raw['status']
			}

		return markets_info

	def parse_data_trades(self, msg):
		""" aggtrade:{'a': 330231197,
			      'p': '0.07460300',
			      'q': '1.50790000',
			      'f': 393565003,
			      'l': 393565004,
			      'T': 1670096404349,
			      'm': True,
			      'M': True}"""
	
		trades_raw = msg['msg']
		market = msg['request_params']['market']

		trades = []
		for trade_raw in trades_raw:
			trade = {
				'id': trade_raw['id'],
				'tm': np.datetime64(trade_raw['time'], 'ms'),
				'Q': float(trade_raw['qty']),
				'R': float(trade_raw['price']),
				'buyer_maker': trade_raw['isBuyerMaker'],
				'custom': {
					'bid_id': None,
					'ask_id': None,
					'event_tm': None,
					'best_match': trade_raw['isBestMatch']
				}
			}

			trades.append(trade)
		return trades

	def parse_data_tickers_C(self, msg):
		tickers_raw = msg['msg']
		if isinstance(tickers_raw, dict):
			return float(tickers_raw['price'])
		tickers = []
		for ticker_raw in tickers_raw:
			ticker = {
				'market': self.symbol_to_infrmt(ticker_raw['symbol']),
				'C': float(ticker_raw['price'])
			}
			tickers.append(ticker)
		return tickers

	def parse_data_tickers_CHL(self, msg):
		# [{"symbol":"1INCH-BTC","lastTradeRate":"0.00011424","bidRate":"0.00011471","askRate":"0.00011505"},]
		tickers_raw = msg['msg']
		tickers = []
		for ticker_raw in tickers_raw:
			ticker = {
				'market': self.symbol_to_infrmt(ticker_raw['symbol']),
				'C': float(ticker_raw['lastPrice']),
				'H': float(ticker_raw['bidPrice']),
				'L': float(ticker_raw['askPrice'])
			}
			tickers.append(ticker)
		return tickers

	def parse_data_ohlcv(self, msg):
		'''
		[
		  [
			1499040000000,	  // 0	Open time
			"0.01634790",	   // 1	Open
			"0.80000000",	   // 2	High
			"0.01575800",	   // 3	Low
			"0.01577100",	   // 4	Close
			"148976.11427815",  // 5	Volume
			1499644799999,	  // 6	Close time
			"2434.19055334",	// 7	Quote asset volume
			308,				// 8	Number of trades
			"1756.87402397",	// 9	Taker buy base asset volume
			"28.46694368",	  // 10	Taker buy quote asset volume
			"17928899.62484339" // 11	Ignore.
		  ]
		]
		'''
		ohlcv_raw = msg['msg']
		ohlcv = []
		for kline_raw in ohlcv_raw:
			kline = {
				'open_tm': kline_raw[0],
				'close_tm': kline_raw[6],
				'o': float(kline_raw[1]),
				'h': float(kline_raw[2]),
				'l': float(kline_raw[3]),
				'c': float(kline_raw[4]),
				'qv': float(kline_raw[7]),
				'bv': float(kline_raw[5]),
				'custom': {
					'trades_count': kline_raw[8],
					'bv_tacker_buy': float(kline_raw[9]),
					'qv_tacker_buy': float(kline_raw[10]),
				}
			}
			ohlcv.append(kline)
		return ohlcv

	def indentify_error_tp(self, msg):
		# raw = msg['msg']
		status_code = msg['status_code']
		if status_code == 0:
			return 'network_down'
		if status_code == -2:
			return 'timeout_error'
		if status_code == 403:
			return 'FAW_lock'
		if status_code == 429:
			return 'too_many_requests'
		if status_code==418:
			return 'too_many_requests'
		if status_code == 503:
			return 'service_unavailable'
		if status_code >= 500:
			return 'repeat'

		if isinstance(msg['msg'], dict):
			err_code = msg['msg'].get('code')

			if err_code:
				if err_code == -1000:
					return 'repeat'
				if err_code == -1001:
					return 'repeat'
				if err_code == -1003:
					return 'too_many_requests'
				if err_code == -1004:
					return 'repeat'
				if err_code == -1121:
					return 'invalid_market'
		return 'unknown_error'


	def parse_decode_error(self, msg):
		pass


	def return_parsing_error(self, msg, E):
		return {
		'tp': 'parsing_error',
		'exception': E,
		'raw': msg,
		'tm': msg['tm']
		}

# def symbol_to_infrmt(self, market):
#	return '-'.join(reversed(market.split('-')))






