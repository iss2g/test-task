
from itertools import count as sequence
import asyncio
import numpy as np
import bisect
from time_funcs import *
from .connection import Connection

from .request_engine import Request

def get_done_task_like():
	f=asyncio.Future()
	f.set_result(None)
	return f

class Requests_distributor:
	max_connections = 1

	limits = {
		'per_period': 600,
		'period_duration': '1m'
	}

	repeat_delay_start = td_to_sd(limits['period_duration']) * 2
	unbun_delay = td_to_sd(limits['period_duration']) * 2
	timeout_total = 60*60*12
	timeout_try = 60
	max_try = 5
	start_time = None
	default_request_config = {
		'repeat_delay_start': repeat_delay_start,
		'unbun_delay': unbun_delay,
		'timeout_total': timeout_total,
		'timeout_try': timeout_try,
		'max_try': max_try,
		'start_time': None,
		'freq':(2,15,5)
	}
	Request.set_default_config(default_request_config)

	def __init__(self, max_weight=600, period_duration='1m'):
		self.metrics_requests = {
			'period': time_s()-time_s()%60,	#timestamp в секундах, отчет лимитов начиная с этого времени
			'period_count': 0,	#израсходовано в отченом периоде
			'period_count_add': 0,	#затрачено на текущие запросы, прибавиться к period_count после их завершения
			'period_count_max': max_weight,
			'period_duration': td_to_sd(period_duration)
		}

		self.connection = Connection(self.callback)
		self.connected=False
		#self.connection.connect_nowait()

		self.pendings = {
			'after_ban': [],
			'zero_try': [],
			'nonzero_try': []
		}
		self.timeout_residue = []
		self.pendings_order = ['after_ban', 'zero_try', 'nonzero_try']

		self.start_zero_try_tasks = {}
		self.start_nonzero_try_tasks = {}
		self.start_after_ban_tasks = {}


		self.distribute_requests_task = get_done_task_like()

		self.request_engines = {}
		self.gr_tasks = {}  # getting_requests
		self.dac_tasks = {}  # delete_after_close
		self.requests_map={}
		
		
		self.FAW_semaphore=asyncio.Semaphore(20)
		self.nonzero_try_order=[]
		
	def set_max_weight(self, max_weight):
		self.metrics_requests['period_count_max'] = max_weight

		
	async def distribute_requests(self):
		if not self.connected:
			await self.connection.connect()
			self.connected=True
	
		self.request_next=None
		while self.pendings['after_ban'] or self.pendings['zero_try'] or self.pendings['nonzero_try']:
			
			if self.start_after_ban_tasks:
				await asyncio.sleep(1)
				continue
		
		


			
			
			if self.request_next:
				request = self.request_next
				self.request_next = None
			elif self.pendings['after_ban']:
				print('too_many_requests')
				
				request = self.pendings['after_ban'].pop(0)
			elif self.pendings['zero_try']:
				request = self.pendings['zero_try'].pop(0)
			else:
				request = self.pendings['nonzero_try'].pop(0)
				self.nonzero_try_order.pop(0)

			if request.is_closed():
				continue

			allowed_weight = self.get_allowed_weight()
			if allowed_weight > request.get_weight():
				await self.FAW_semaphore.acquire()

				track_id = self.connection.req_low(request.params)
				self.requests_map[track_id] = request
				self.on_request_update_metrics_requests(track_id)
				
			else:
				self.request_next = request
				await self.sleep_to_new_period()
		
	def add_request(self, request):
		self.start_zero_try_tasks[request.id] = asyncio.create_task(self.for_start_zero_try(request))
		
	def add_request_engine(self, request_engine):
		self.request_engines[request_engine.id] = request_engine
		self.add_getting_requests_task(request_engine)
		self.dac_tasks[request_engine.id] = asyncio.create_task(self.delete_after_close(request_engine))
		
	def add_getting_requests_task(self, request_engine):
		self.gr_tasks[request_engine.id] = asyncio.create_task(self.getting_requests(request_engine))
		return request_engine.id
		
	def remove_getting_requests_task(self, task_id):
		#print(1)
		getting_requests_task = self.gr_tasks.pop(task_id)
		getting_requests_task.cancel()
		
	async def getting_requests(self, request_engine):
		while True:
			request = await request_engine.get_next_request()
			if request:
				self.add_request(request)
			else:
				self.remove_getting_requests_task(request_engine.id)
				return
		
	async def delete_after_close(self, request_engine):
		await request_engine.get_future()
		del self.request_engines[request_engine.id]
		del self.dac_tasks[request_engine.id]
		
	def callback(self, msg, track_id):
		self.FAW_semaphore.release()
		self.on_result_update_metrics_requests(track_id)
		request = self.requests_map.pop(track_id)
		request.report(msg)

		if not request.is_closed():
			if msg['error_tp'] == 'too_many_requests':
				self.start_after_ban_tasks[request.id] = asyncio.create_task(self.for_start_after_ban(request))
			else:
				self.start_nonzero_try_tasks[request.id] = asyncio.create_task(self.for_start_nonzero_try(request))
		
	async def for_start_zero_try(self, request):
		await request.get_start_allowed_future()
		if not request.is_closed():
			self.pendings['zero_try'].append(request)
		del self.start_zero_try_tasks[request.id]

		if self.distribute_requests_task.done():
			self.distribute_requests_task = asyncio.create_task(self.distribute_requests())
		
	async def for_start_nonzero_try(self, request):
		await request.get_start_allowed_future()
		if not request.is_closed():
			timeout_residue = request.timeout_residue()
			index = bisect.bisect(self.nonzero_try_order, timeout_residue)
			self.nonzero_try_order.insert(index, timeout_residue)
			self.pendings['nonzero_try'].insert(index, request)
		del self.start_nonzero_try_tasks[request.id]
		if self.distribute_requests_task.done():
			self.distribute_requests_task = asyncio.create_task(self.distribute_requests())
		
	async def for_start_after_ban(self, request):

		await request.get_start_allowed_future()
		if not request.is_closed():
			self.pendings['after_ban'].append(request)
		del self.start_after_ban_tasks[request.id]
		if self.distribute_requests_task.done():
			self.distribute_requests_task = asyncio.create_task(self.distribute_requests())
		
	def on_request_update_metrics_requests(self, track_id):
		weight = self.requests_map[track_id].get_weight()

		mr = self.metrics_requests
		period_is_actual = mr['period'] + mr['period_duration'] > time_s()

		if not period_is_actual and not mr['period_count_add']:
			mr['period'] = time_s()-time_s()%60
			mr['period_count'] = 0
		mr['period_count_add'] += weight
		
	def on_result_update_metrics_requests(self, track_id):
		weight = self.requests_map[track_id].get_weight()

		mr = self.metrics_requests
		period_is_actual = mr['period'] + mr['period_duration'] > time_s()

		if not mr['period_count'] or not period_is_actual:
			mr['period_count'] = 0
			mr['period'] = time_s()-time_s()%60

		mr['period_count_add'] -= weight
		mr['period_count'] += weight
		
		
		
	def get_allowed_weight(self):
		mr = self.metrics_requests
		period_is_actual = mr['period'] + mr['period_duration'] > time_s()

		if period_is_actual:
			return mr['period_count_max'] - mr['period_count'] - mr['period_count_add']
		else:
			return mr['period_count_max'] - mr['period_count_add']
		
	async def sleep_to_new_period(self):
		mr = self.metrics_requests
		sleep = mr['period'] + mr['period_duration'] - time_s()
		await asyncio.sleep(sleep)
		
	async def close(self):
		# закрыть соендинение
		# закрыть все задачи
		# закрыть все запросы
		# закрыть все request_engines
		await self.connection.close()

		self.distribute_requests_task.cancel()

		for request_engine in self.request_engines:
			request_engine.close()
		for tid, task in self.start_zero_try_tasks:
			task.cancel()
		for tid, task in self.start_nonzero_try_tasks:
			task.cancel()
		for tid, task in self.start_after_ban_tasks:
			task.cancel()
		for tid, task in self.gr_tasks:
			task.cancel()
		for tid, task in self.dac_tasks:
			task.cancel()

		self.__init__(self.metrics_requests['period_count_max'])

