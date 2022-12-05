from itertools import count as sequence
import asyncio

from time_funcs import *

from .dt_instructions import dt_instructions

def get_done_task_like():
	f=asyncio.Future()
	f.set_result(None)
	return f

class Request_engine:
	id_sequence = sequence(1)
	Exceptions=[]
	def __init__(self, params, config):
		self.id = next(self.id_sequence)
		self.DTI=dt_instructions[params['data_tp']]
		
		self.params=self.DTI.normalize_params(params)

		self.config = config

		self.future = asyncio.Future()
		self.callback = self.future.set_result

		self.requests = []
		self.requests_futures = []


		self.getting_results_task = get_done_task_like()
		
		self.data_all = None
		self.data_new=None

		self.closed=False
		

	async def getting_results(self):
		if self.DTI.request_schema=='sequential':
			result=await self.request.future
			if result['tp']=='data':
				self.data_new=result['data']
				self.data_all=self.DTI.join_data(self.data_new, self.data_all)
			else:
				self.Exceptions.append(result)
				msg=self.get_msg(self.data_all, result['err_tp'], result['err_info'], result['err_history'])
				self.callback(msg)
				self.close_internal()
				return

			if not self.get_next_request_params_nowait():
				self.close_internal()
				msg=self.get_msg(self.data_all)
				self.callback(msg)
			#print('return')
		else:
			raise NotImplementedError

	async def get_next_request(self):
		if self.closed:
			return None
			
		request_params = await self.get_next_request_params()
		
		if self.closed:
			return None
		if not request_params:
			return None
		
		request = Request(request_params, self.config)
		self.request=request
		#self.requests_futures=append(request.future)

		if self.getting_results_task.done():
			self.getting_results_task = asyncio.create_task(self.getting_results())
		return request
	
		
	async def get_next_request_params(self):
		if self.DTI.request_schema=='sequential':

			await self.getting_results_task
			request_params_next=self.DTI.get_next_params(self.params, self.data_new, self.data_all)
			return request_params_next
		else:
			raise NotImplementedError

	def get_next_request_params_nowait(self):
		if self.DTI.request_schema=='sequential':
			#await self.getting_results_task
			request_params_next=self.DTI.get_next_params(self.params, self.data_new, self.data_all)
			return request_params_next
		else:
			raise NotImplementedError
			
	
		
	def get_msg(self, data=None, err_tp=None, err_info=None, err_history=None):
		msg={
			'data':None,
			'error':None
		}
		if data!=None:
			msg['data']=data
		if err_tp or err_info or err_history:
			msg['error']={}
			msg['error']['params']=self.request.params
		
		if err_tp:
			msg['error']['err_tp']=err_tp
		if err_info:
			msg['error']['err_info']=err_info
		if err_history:
			msg['error']['err_history']=err_history
		return msg
		

	def get_future(self):
		return self.future


	def close_internal(self):
		self.closed = True
		self.getting_results_task.cancel()
		self.request.close()


	def close(self):
		self.closed = True
		self.getting_results_task.cancel()
		for request in self.requests:
			request.close()
		if not self.future.done():
			self.callback(None)


class Request:
	id_sequence = sequence(1)
	default_config = {}

	@classmethod
	def set_default_config(self, config):
		self.default_config.update(config)
		

	#@classmethod
	#def get_weight(params):
	
	def __init__(self, params, config):
		self.id = next(self.id_sequence)
		self.DTI=dt_instructions[params['data_tp']]
		self.weight=self.DTI.get_weight(params)
	

		self.params = params

		self.future = asyncio.Future()
		self.callback = self.future.set_result
		
		self.config = {
			**self.default_config,
			**config
		}

		self.freq=self.config.get('freq') or (2,10,5)

		self.try_num = 0
		self.closed = False

		self.start_delay_task = None
		self.start_after_delay = False

		self.init_tm = time_s()
		start_time = self.config.get('start_tm')
		self.start_tm = start_time if start_time else self.init_tm

		self.timeout_tm = self.start_tm + self.config.get('timeout_total')
		self.timeout_task = asyncio.create_task(self.timeout_coro())


		self.delay_task = self.run_delay()
		
		self.err_history={}
		
		
	def get_future(self):
		return self.future
		


	def get_weight(self):
		return self.weight
	#	
		
		
		
	async def timeout_coro(self):
		await asyncio.sleep(self.timeout_tm-time_s())
		if not self.is_closed():
			self.on_timeout_total()
		
	def run_delay(self, delay=None):
		if not delay:
			if not self.try_num and self.config.get('start_time'):
				delay = self.config['start_time'] - time_s()
				return asyncio.create_task(self.wait_for_delay(delay))
			if self.try_num:
				delay = self.calculate_delay()
				return asyncio.create_task(self.wait_for_delay(delay))

			else:
				done_task = asyncio.Future()
				done_task.set_result(None)
				return done_task
		else:
			return asyncio.create_task(self.wait_for_delay(delay))
		
	def calculate_delay(self):
		to_timeout = self.timeout_tm - time_s()

		return min(
			(self.freq[0]+self.freq[2]*self.try_num),
			self.freq[1]
			)

#		if self.try_num==0:
#			return 0
#		else:
#			return min(self.freq[0]+self.freq[2]*self.try_num
#		
#		elif self.try_num
#			
#		elif self.try_num == 1 and to_timeout > self.config['repeat_delay_start']:
#			return self.config['repeat_delay_start']
#		else:
#			try_weight_sum = sum(range(self.try_num, self.config.try_max))
#			weight_part = self.try_count / try_weight_sum
#			delay = int(to_timeout * weight_part)
#			if weight_part == 1:
#				delay -= self.config['timeout_try']
#			return int(to_timeout * weight_part)
		
	async def wait_for_delay(self, delay):
		await asyncio.sleep(delay)
		
	def delay_start(self, start_method):
		return asyncio.create_task(self.wait_for_start_time(start_method))
		
	def start_is_allowed(self):
		if not self.is_closed() and self.delay_task.done():
			return True
		return False
		
	def get_start_allowed_future(self):
		return self.delay_task
		
	def is_closed(self):
		return self.closed
			
	def report(self, msg):
		#print(msg)
		getattr(self, f'on_{msg["tp"]}')(msg)
		
	def on_data(self, msg):
		self.callback(msg)
		self.close()
		
	def on_error(self, msg):

		getattr(self, f'on_error_{msg["error_tp"]}')(msg)
		
	def on_error_network_down(self, msg):
		#print('err')
		self.on_error_repeat(msg)
		
	def on_error_timeout(self, msg):
		self.on_error_repeat(msg)
		
	def on_error_service_unavailable(self, msg):
		self.on_error_repeat(msg)
		
	def on_error_repeat(self, msg):
		print(self.try_num)
		self.try_num += 1
		if self.try_num == self.config['max_try']:

			self.callback({
				'tp':'error',
				'err_tp':msg['error_tp'],
				'err_info':{'msg':msg['msg'], 'about':msg['about_msg']},
				'err_history':self.err_history
			})
			self.close()
			return
		#self.try_num += 1
		self.err_history[msg['tm']]={
			'err_tp':msg['error_tp'],
			'err_info':{'msg':msg['msg'], 'about':msg['about_msg']}
		}
		self.delay_task = self.run_delay()
		
	def on_error_too_many_requests(self, msg):

		self.delay_task = self.run_delay(self.config['unbun_delay'])
		self.err_history[msg['tm']]={
			'err_tp':msg['error_tp'],
			'err_info':{'msg':msg['msg'], 'about':msg['about_msg']}
		}
		
	def on_error_invalid_market(self, msg):

		self.callback({
			'tp':'error',
			'err_tp':'invalid_market',
			'err_info':{'msg':msg['msg'], 'about':msg['about_msg']},
			'err_history':self.err_history
		
		})
		self.close()
	
	def on_error_unknown_error(self, msg):
		self.callback({
			'tp':'error',
			'err_tp':'unknown_error',
			'err_info':{'msg':msg['msg'], 'about':msg['about_msg']},
			'err_history':self.err_history
		
		})
		self.close()
	
		
	def on_parsing_error(self, msg):
		#print(msg)
		#parsing_error.append(msg)
		
		#msg.update({'err_history':self.err_history})
		print('parsing_error')
		self.callback({
			'tp':'error',
			'err_tp':'parsing_error',
			'err_info':{'E':msg['exception'], 'raw':msg['raw']},
			'err_history':self.err_history
		})
		self.close()
		
	def on_timeout_total(self):
		self.callback({
			'tp':'error',
			'err_tp': 'timeout_total',
			'err_history': self.err_history
		})
		self.close()
		
		
	def close(self):
		self.timeout_task.cancel()
		self.delay_task.cancel()
		self.closed = True
		
		if not self.future.done():
			self.callback(None)

	def timeout_residue(self):
		return self.timeout_tm - time_s()




