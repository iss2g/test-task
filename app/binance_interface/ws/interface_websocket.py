import numpy as np
import asyncio
from binance_interface.ws.interface import Interface_ws
from time_funcs import *	
	
tm_ranks_order=['m', 'h']
def seconds_to_td(seconds):
    rank='s'
    tm_units=seconds
    for rank_next in tm_ranks_order:
        if tm_units%60:
            break
        else:
            tm_units=tm_units//60
            rank=rank_next
    return f'{tm_units}{rank}'



class Interface_websocket(Interface_ws):
	def __init__(self, callback=None):
		if callback:
			self.callback=self.wrap_callback_to_postprocessing(callback)
		else:
			self.callback=None
		super().__init__()
		
	def set_callback(self, callback):
		if self.callback:
			raise Exception('the callback is alrady set')
		self.callback=self.wrap_callback_to_postprocessing(callback)

	def subscribe_ohlcv_updates(self, markets, step=60, callback=None):
		assert self.callback or callback, 'the callback must be passed at the instance or method level'
		
		if callback:
			callback=self.wrap_callback_to_postprocessing(callback)
		else:
			callback=self.callback
		
		if not isinstance(markets, list):
			markets=[markets]
		
		interval=seconds_to_td(step)
		stream_ids=[]
		for market in markets:
			stream_id=self.sub_ohlcv_up(market, interval, callback)
			stream_ids.append(stream_id)
		return stream_ids
	
	def unsubscribe_ohlcv_updates(self, stream_ids):
		if not isinstance(stream_ids, list):
			stream_ids=[stream_ids]
	
		for stream_id in stream_ids:
			self.close_stream(stream_id)

	def resubscribe_ohlcv_updates(self, stream_ids):
		if not isinstance(stream_ids, list):
			stream_ids=[stream_ids]
	
		for stream_id in stream_ids:
			self.restart_stream(stream_id)

	def wrap_callback_to_postprocessing(self, callback):
		def callback_with_postprocessing(msg):

			if not self.is_ignored_msg(msg):

				msg=self.postprocess_msg(msg)
				callback(msg)
		return callback_with_postprocessing
			
			
	def postprocess_msg(self, msg):
		if msg['tp']=='stream_state':
			if msg['state']=='sended':
				return self.on_sended(msg)
			elif msg['state']=='pending':
				return self.on_pending(msg)
		else:
			return self.on_data(msg)
		
		
	def is_ignored_msg(self , msg):
		if msg['tp']=='stream_state':
			if msg['state'] in ['sending', 'success', 'active']:
				return True
		return False
		
	def on_pending(self, msg):
		return {
			'tp':'STOP',
			'sid':msg['stream_id'],
			'mkt':self.streams[msg['stream_id']].request.params['market'],
			'step':td_to_sd(self.streams[msg['stream_id']].request.params['interval'])
		}			 

	def on_sended(self, msg):
		return {
			'tp':'START',
			'sid':msg['stream_id'],
			'deadline':msg['deadline'],
			'mkt':self.streams[msg['stream_id']].request.params['market'],
			'step':td_to_sd(self.streams[msg['stream_id']].request.params['interval'])
			
		}

	def on_data(self, msg):

		data=msg['data']
		return {
			'tp':'UPDATE',
			'sid':msg['stream_id'],
			'tm':np.datetime64(data['open_tm'], 'ms'),
			'O':data['o'],
			'H':data['h'],
			'L':data['l'],
			'C':data['c'],
			'V':data['bv'],
			'BV':data['qv'],
			'isClosed':data['custom']['closed'],
			'mkt':self.streams[msg['stream_id']].request.params['market'],
			'step':td_to_sd(self.streams[msg['stream_id']].request.params['interval'])
		}
	
	
	async def close(self):
		await self.reboot()

