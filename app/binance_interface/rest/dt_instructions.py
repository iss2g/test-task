from copy import deepcopy as copy
import numpy as np
from time_funcs import *

class Instruction_dt():
	weight_map={
		'ohlcv':1,
		'trades':1,
		'markets':10,

	}
	
	request_schema='sequential'	# or 'synchronous'


	def normalize_params(params):
		return params
		
	@classmethod
	def get_weight(self, params):
		return self.weight_map[params['data_tp']]
	
	def get_next_params(params, data_new=None, data_all=None):
		if data_new or data_all:
			return None
		return params
	
	def join_data(data_new, data_all=None):
		return data_new

class Instruction_ohlcv(Instruction_dt):
	'''
	start not None, end not None, limit - None/not None:
	start not None, limit not None, end None:
	start None, limit None, end None
	start None limit None, end not None
	start None , limit not None ,end not None
	limit: None, 0 , >0
	'''
	def normalize_params(params):
		start=params['start']
		end=params['end']
		limit=params['limit']
		interval=params['interval']

		if start!=None:
			start=np.datetime64(start, 's')
			start=round_dt64(start, interval, 'down')
			start=start.astype('uint64')
		if end!=None:
			end=np.datetime64(end, 's')
			end=round_dt64(end, interval, 'up')
			end=end.astype('uint64')
		
		if not limit:
			limit=None		


		if end and not limit and not start:
			start=0
					
		params_normal={
			'req_tp':'get',
			'data_tp':'ohlcv',
			'market':params['market'],
			'interval':params['interval'],
			'start':start,
			'end':end,
			'limit':limit
		}
		return params_normal 
		
	def get_weight(params):
		return 1
	
	def get_next_params(params, data_new, data_all):
		market=params['market']
		interval=params['interval']
		start=params['start']
		end=params['end']
		limit=params['limit']
		
		if limit!=None and data_all!=None:
			if len(data_all)>=limit:
				return None
		
		if data_new!=None:
			if not limit and not start and not end:
				return None
			if len(data_new)<1000:
				return None

			
			
			last_kline_tm=data_new[-1]['open_tm']
			if start!=None:
				req_start=last_kline_tm
				
			if end!=None:
				if req_start>=end:
					return None
				
			
		else:
			if start!=None:
				req_start=start	
			else:
				req_start=None

		return {
			'req_tp':'get',
			'data_tp':'ohlcv',
			'market':market,
			'interval':interval,
			'start':req_start,
			'end':None,
			'limit':None
		}
		

	def join_data(data_new, data_all):
		if data_all is None:
			return data_new
		if len(data_new)==0:
			return data_all
		if len(data_all)==0:
			return data_new
		
		first_new_index=data_new[0]['open_tm']
		
		data=copy(data_all)
		for i in range(1, len(data)+1):
			row = data[-i]
			if i == 1 and first_new_index > row['open_tm']:
				data.extend(data_new)
				return data
				
			if first_new_index == row['open_tm']:
				data[-i:] = data_new
				return data
				
		raise Exception('слияние данных работате не правильно')
		
class Instruction_markets(Instruction_dt):
	pass
	
class Instruction_trades(Instruction_dt):
	pass
	
class Instruction_tickers_C(Instruction_dt):
	def get_weight(params):
		if params.get('market'):
			return 1
		else:
			return 2
	
class Instruction_tickers_CHL(Instruction_dt):
	def get_weight(params):
		if params.get('market'):
			return 1
		else:
			return 40
			
class Instruction_orderbook(Instruction_dt):
	def get_weight(params):
		depth=params['depth']
		if depth<=100:
			return 1
		else:
			return depth//100
	

dt_instructions={
	'ohlcv':Instruction_ohlcv,
	'markets':Instruction_markets,
	'orderbook':Instruction_orderbook,
	'trades':Instruction_trades,
	'tickers_C':Instruction_tickers_C,
	'tickers_CHL':Instruction_tickers_CHL
}
