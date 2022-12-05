from .requests_distributor import Requests_distributor
from .request_engine import Request_engine

class Interface(Requests_distributor):
		
	def get_ohlcv(self, market, interval='1m', start=None, end=None, limit=None, **config):
		for attr in config.keys():
			if attr not in self.default_request_config:
				raise Exception('!')
		params = {
			'req_tp': 'get',
			'data_tp': 'ohlcv',
			'market': market,
			'interval': interval,
			'start': start,
			'end': end,
			'limit': limit
		}
		request_engine = Request_engine(params, config)
		self.add_request_engine(request_engine)
		return request_engine.get_future()
		
	def get_markets(self, **config):
		for attr in config.keys():
			if attr not in self.default_request_config:
				raise Exception('!')
		params = {
			'req_tp': 'get',
			'data_tp': 'markets',
		}
		request_engine = Request_engine(params, config)
		self.add_request_engine(request_engine)
		return request_engine.get_future()

	def get_orderbook(self, market, depth=1000, **config):
		for attr in config.keys():
			if attr not in self.default_request_config:
				raise Exception('!')
				
		params={
			'req_tp':'get',
			'data_tp':'orderbook',
			'market':market,
			'depth':depth
		
		}
		
		request_engine=Request_engine(params, config)
		self.add_request_engine(request_engine)
		return request_engine.get_future()
		
	def get_trades(self, market, limit=1000, **config):
		for attr in config.keys():
			if attr not in self.default_request_config:
				raise Exception('!')
				
		params={
			'req_tp':'get',
			'data_tp':'trades',
			'market':market,
			'limit':limit
		
		}
		
		request_engine=Request_engine(params, config)
		self.add_request_engine(request_engine)
		return request_engine.get_future()
	
	
	def get_tickers_C(self, market=None, **config):
		for attr in config.keys():
			if attr not in self.default_request_config:
				raise Exception('!')
		params={
			'req_tp':'get',
			'data_tp':'tickers_C',
			'market':market
		}	
		request_engine=Request_engine(params, config)
		self.add_request_engine(request_engine)
		return request_engine.get_future()
	
	
	
	def get_tickers_CHL(self, market=None, **config):
		for attr in config.keys():
			if attr not in self.default_request_config:
				raise Exception('!')
		params={
			'req_tp':'get',
			'data_tp':'tickers_CHL',
			'market':market
		}		
		request_engine=Request_engine(params, config)
		self.add_request_engine(request_engine)
		return request_engine.get_future()
