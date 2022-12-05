from binance_interface.rest.interface import Interface

import pandas as pd
		
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


class Interface_rest(Interface):
	
	def __init__(self, weight_limit=600,  freq=None):
		self._freq=freq or (30, 300, 20)
		print(self._freq)
		super().__init__(weight_limit)
	
	async def getLastPrice(self, mkt=None, max_tries=0, freq=None):	
		result=await self.get_tickers_C(mkt, max_try=max_tries, freq=freq or self._freq)
		
		err=None
		errEx=None
		
		if result['data']!=None:
			if isinstance(result['data'], list):
				data={}
				for item in result['data']:
					data[item['market']]=item['C']
			
			else:
				data=result['data']
		else:
			err=result['error'].get('err_tp')
			errEx=result['error'].get('err_info')
			
		return {
			'out':data,
			'err':err,
			'errEx':errEx		
		}
			
	async def getOhlcv(self, mkt, step=60, startTm=None, endTm=None, max_tries=0, freq=None):
		future=self.get_ohlcv(mkt, seconds_to_td(step), startTm, endTm, max_try=max_tries, freq=freq or self._freq)
		result=await future
		
		
		err=None
		errEx=None
			
		if result['data']!=None:
			df_temp=pd.DataFrame(result['data'])
			df_temp['tm']=pd.to_datetime(df_temp['open_tm'], unit='ms')
			df=pd.DataFrame()
			#print(df_temp)
			df[['tm', 'O', 'H', 'L', 'C', 'V', 'BV']]=df_temp[['tm', 'o', 'h', 'l', 'c', 'bv', 'qv']]
			df=df.set_index('tm')
		else:
			df=None
			if result['error']:
				err=result['error'].get('err_tp')
				errEx=result['error'].get('err_info')
			
		
		return {
			'out':df,
			'err':err,
			'errEx':errEx		
		}
			
	async def getMktsInfo(self, max_tries=0, freq=None):
		#print('get')
		future=self.get_markets(max_try=max_tries, freq=freq or self._freq)
		result=await future
		
		markets_info={}
		err=None
		errEx=None
		if result['data']!=None:
			for market, info in result['data'].items():
				markets_info[market]={
					'mkt':market,
					'symbol':info['symbol'],
					'base':info['base'],
					'quote':info['quote'],
					'isActive':info['is_active']
				}

				
		else:
			markets_info=None
			if result['error']:
				err=result['error'].get('err_tp')
				errEx=result['error'].get('err_info')
			
		return {
			'out':markets_info,
			'err':err,
			'errEx':errEx		
		}


		

